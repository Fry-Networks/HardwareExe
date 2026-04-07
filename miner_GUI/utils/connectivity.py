"""Optimized connectivity and network utilities."""

import time
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor, Future
from importlib.util import find_spec

HAVE_REQUESTS = find_spec("requests") is not None

from miner_GUI.utils.data import log_step


class ConnectivityManager:
    """Manages network connectivity checks with optimization for startup."""
    
    def __init__(self):
        self.last_connectivity_check = 0
        self.last_connectivity_result = None
        self.last_public_ip_check = 0
        self.last_public_ip = None
        self.connectivity_cache_ttl = 30  # 30 seconds
        self.ip_cache_ttl = 300  # 5 minutes
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="connectivity")
    
    def is_internet_up_cached(self, timeout: float = 2.0, force_check: bool = False) -> bool:
        """Check internet connectivity with caching."""
        current_time = time.time()
        
        # Return cached result if still valid
        if not force_check and self.last_connectivity_result is not None:
            if current_time - self.last_connectivity_check < self.connectivity_cache_ttl:
                log_step("Connectivity cache hit", {
                    "result": self.last_connectivity_result,
                    "age": current_time - self.last_connectivity_check
                })
                return self.last_connectivity_result
        
        # Perform actual check
        try:
            if not HAVE_REQUESTS:
                # Fallback: assume online if we can't check
                result = True
            else:
                # Use Google's connectivity check endpoint
                import requests as req
                response = req.get(
                    "http://clients3.google.com/generate_204", 
                    timeout=timeout
                )
                result = response.status_code == 204
            
            # Cache the result
            self.last_connectivity_check = current_time
            self.last_connectivity_result = result
            
            log_step("Connectivity check", {"result": result, "timeout": timeout})
            return result
            
        except Exception as e:
            log_step("Connectivity check failed", {"error": str(e), "timeout": timeout})
            # Cache negative result but for shorter time
            self.last_connectivity_check = current_time
            self.last_connectivity_result = False
            return False
    
    def get_public_ip_cached(self, timeout: float = 2.0, force_check: bool = False) -> Optional[str]:
        """Get public IP with caching."""
        current_time = time.time()
        
        # Return cached result if still valid
        if not force_check and self.last_public_ip is not None:
            if current_time - self.last_public_ip_check < self.ip_cache_ttl:
                log_step("Public IP cache hit", {
                    "ip": self.last_public_ip,
                    "age": current_time - self.last_public_ip_check
                })
                return self.last_public_ip
        
        # Perform actual check
        try:
            if not HAVE_REQUESTS:
                return None
                
            import requests as req
            response = req.get(
                "https://api.ipify.org",
                params={"format": "json"},
                timeout=timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                ip_value = data.get("ip") if isinstance(data, dict) else None
                
                if isinstance(ip_value, str) and ip_value:
                    # Cache the result
                    self.last_public_ip_check = current_time
                    self.last_public_ip = ip_value
                    
                    log_step("Public IP check", {"ip": ip_value, "timeout": timeout})
                    return ip_value
            
            return None
            
        except Exception as e:
            log_step("Public IP check failed", {"error": str(e), "timeout": timeout})
            return None
    
    def check_connectivity_async(self, timeout: float = 2.0, 
                                callback: Optional[Callable[[bool], None]] = None) -> Future:
        """Check connectivity asynchronously."""
        def _check():
            result = self.is_internet_up_cached(timeout, force_check=True)
            if callback:
                callback(result)
            return result
        
        return self.executor.submit(_check)
    
    def get_public_ip_async(self, timeout: float = 2.0,
                          callback: Optional[Callable[[Optional[str]], None]] = None) -> Future:
        """Get public IP asynchronously."""
        def _get_ip():
            result = self.get_public_ip_cached(timeout, force_check=True)
            if callback:
                callback(result)
            return result
        
        return self.executor.submit(_get_ip)
    
    def prefetch_network_info(self):
        """Prefetch network information in background for later use."""
        log_step("Prefetching network information")
        
        # Start both checks in parallel
        connectivity_future = self.check_connectivity_async(timeout=1.0)
        ip_future = self.get_public_ip_async(timeout=1.0)
        
        return connectivity_future, ip_future
    
    def get_cache_status(self) -> dict:
        """Get cache status for debugging."""
        current_time = time.time()
        
        return {
            "connectivity": {
                "cached": self.last_connectivity_result,
                "age": current_time - self.last_connectivity_check if self.last_connectivity_check > 0 else None,
                "valid": (current_time - self.last_connectivity_check) < self.connectivity_cache_ttl if self.last_connectivity_check > 0 else False
            },
            "public_ip": {
                "cached": self.last_public_ip,
                "age": current_time - self.last_public_ip_check if self.last_public_ip_check > 0 else None,
                "valid": (current_time - self.last_public_ip_check) < self.ip_cache_ttl if self.last_public_ip_check > 0 else False
            }
        }


# Global connectivity manager instance
connectivity_manager = ConnectivityManager()


# Convenience functions for backward compatibility
def is_internet_up(timeout: float = 2.0) -> bool:
    """Check if internet is available (optimized with caching)."""
    return connectivity_manager.is_internet_up_cached(timeout)


def get_public_ip(timeout: float = 2.0) -> Optional[str]:
    """Get public IP address (optimized with caching)."""
    return connectivity_manager.get_public_ip_cached(timeout)


def prefetch_network_info():
    """Prefetch network information for faster later access."""
    return connectivity_manager.prefetch_network_info()