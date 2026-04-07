import json, re, uuid
try:
    import psutil
except ImportError:
    psutil = None

info = {
    'psutil_available': bool(psutil),
    'interfaces': [],
    'uuid_getnode': uuid.getnode()
}

mac_regex = re.compile(r'^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$')

if psutil:
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, lst in addrs.items():
            stat = stats.get(name)
            entry = {
                'name': name,
                'isup': getattr(stat, 'isup', None),
                'speed': getattr(stat, 'speed', None),
                'mtu': getattr(stat, 'mtu', None),
                'mac_candidates': [],
                'addresses': []
            }
            for a in lst:
                addr = getattr(a, 'address', '') or ''
                fam = getattr(a, 'family', None)
                entry['addresses'].append({'family': fam, 'address': addr})
                if mac_regex.match(addr) and addr != '00:00:00:00:00:00':
                    entry['mac_candidates'].append(addr)
            info['interfaces'].append(entry)
    except Exception as e:
        info['error'] = str(e)

print(json.dumps(info, indent=2))
