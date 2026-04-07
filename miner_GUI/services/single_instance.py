"""Single instance management for preventing multiple miner instances."""

from PySide6 import QtCore
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QtCore.QObject):
    """Manages single instance behavior using local socket IPC."""
    
    wakeRequested = QtCore.Signal()
    
    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.server = None
    
    def start_or_signal(self) -> bool:
        """Start server or signal existing instance.
        
        Returns:
            True if this is the first instance (server started successfully)
            False if another instance exists (signal sent)
        """
        # First, try to connect to an existing instance
        sock = QLocalSocket()
        sock.connectToServer(self.key, QtCore.QIODevice.OpenModeFlag.WriteOnly)
        
        if sock.waitForConnected(1000):
            # Another instance is running
            sock.write(b"SHOW\n")
            sock.flush()
            sock.waitForBytesWritten(500)
            sock.disconnectFromServer()
            sock.waitForDisconnected(500)
            return False
        
        # No existing instance found, clean up any stale server
        QLocalServer.removeServer(self.key)
        
        # Try to start the server
        self.server = QLocalServer(self)
        if not self.server.listen(self.key):
            # Failed to start server - this shouldn't happen after removeServer
            return False
        
        self.server.newConnection.connect(self._on_new_connection)
        return True
    
    def _on_new_connection(self) -> None:
        """Handle new connection from another instance."""
        if not self.server:
            return
        sock = self.server.nextPendingConnection()
        if not sock:
            return
        sock.readyRead.connect(lambda s=sock: self._read_and_wake(s))
    
    def _read_and_wake(self, sock: QLocalSocket) -> None:
        """Read data and emit wake signal."""
        try:
            _ = sock.readAll()
        except Exception:
            pass
        
        self.wakeRequested.emit()
        
        try:
            sock.disconnectFromServer()
        except Exception:
            pass