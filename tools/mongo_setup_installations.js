// Mongosh script to set up main.installations and related indexes
// Usage:
//   mongosh your-uri tools/mongo_setup_installations.js

(function () {
  const dbm = db.getSiblingDB("main");

  function collExists(name) {
    try {
      return dbm.getCollectionInfos({ name }).length > 0;
    } catch (e) {
      // Fallback for older servers
      return dbm.getCollectionNames().indexOf(name) >= 0;
    }
  }

  // 1) Create 'installations' with a light validator (idempotent)
  if (!collExists("installations")) {
    dbm.createCollection("installations", {
      validator: {
        $jsonSchema: {
          bsonType: "object",
          required: [
            "miner_key",
            "install_id",
            "minerCode",
            "version_installed",
            "first_installed_at",
            "last_seen_at",
            "is_installed",
          ],
          properties: {
            miner_key: { bsonType: "string" },
            install_id: { bsonType: "string" },
            minerCode: { bsonType: "string" },
            version_installed: { bsonType: "string" },
            hostname: { bsonType: "string" },
            os: { bsonType: "string" },
            first_installed_at: { bsonType: "date" },
            last_seen_at: { bsonType: "date" },
            is_installed: { bsonType: "bool" },
          },
        },
      },
      validationLevel: "moderate",
    });
    print("Created collection: installations");
  } else {
    print("Collection already exists: installations");
  }

  // 2) Indexes for 'installations'
  dbm.installations.createIndex(
    { miner_key: 1, install_id: 1 },
    { unique: true, background: true },
  );
  dbm.installations.createIndex(
    { miner_key: 1, last_seen_at: -1 },
    { background: true },
  );
  // Optional TTL: expire records 14 days after last_seen_at
  dbm.installations.createIndex(
    { last_seen_at: 1 },
    { expireAfterSeconds: 1209600, background: true },
  );

  // 3) Helpful indexes on 'devices'
  dbm.devices.createIndex({ miner_key: 1 }, { unique: true, background: true });
  dbm.devices.createIndex({ software_version_needed: 1 }, { background: true });

  // 4) One-time migration: isInstalled -> is_installed (safe if already done)
  try {
    const res = dbm.devices.updateMany(
      { isInstalled: { $type: "bool" } },
      [
        { $set: { is_installed: "$isInstalled" } },
        { $unset: "isInstalled" },
      ],
    );
    if (res && res.modifiedCount) {
      print(`Migrated isInstalled -> is_installed on ${res.modifiedCount} docs`);
    }
  } catch (e) {
    print(`Migration check failed: ${e.message}`);
  }

  // 5) Helper queries (functions)
  // Active installs for a given miner_key in the last N minutes (default 5)
  globalThis.activeInstalls = function (minerKey, windowMinutes = 5) {
    const cutoff = new Date(Date.now() - windowMinutes * 60 * 1000);
    return dbm.installations
      .find(
        { miner_key: minerKey, last_seen_at: { $gte: cutoff } },
        { _id: 0, install_id: 1, minerCode: 1, version_installed: 1, hostname: 1, last_seen_at: 1 },
      )
      .sort({ last_seen_at: -1 })
      .toArray();
  };

  // Does a conflict exist for this miner_key (other install_id is active)?
  globalThis.hasConflict = function (minerKey, installId, windowMinutes = 5) {
    const cutoff = new Date(Date.now() - windowMinutes * 60 * 1000);
    return !!dbm.installations.findOne(
      {
        miner_key: minerKey,
        install_id: { $ne: installId },
        last_seen_at: { $gte: cutoff },
      },
      { _id: 1 },
    );
  };

  // Summary: active installs per key in the last N minutes
  globalThis.installsByKey = function (windowMinutes = 5) {
    const cutoff = new Date(Date.now() - windowMinutes * 60 * 1000);
    return dbm.installations
      .aggregate([
        { $match: { last_seen_at: { $gte: cutoff } } },
        {
          $group: {
            _id: "$miner_key",
            active: { $sum: 1 },
            latest: { $max: "$last_seen_at" },
          },
        },
        { $sort: { active: -1 } },
      ])
      .toArray();
  };

  // Manual cleanup: delete installs older than N days (use if TTL isn’t set or changed)
  globalThis.pruneInstalls = function (olderThanDays = 30) {
    const cutoff = new Date(Date.now() - olderThanDays * 24 * 60 * 60 * 1000);
    return dbm.installations.deleteMany({ last_seen_at: { $lt: cutoff } });
  };

  print("Setup complete. Helper functions loaded: activeInstalls, hasConflict, installsByKey, pruneInstalls");
})();

