# LAMDA Connection Troubleshooting

Default target: `127.0.0.1:65000` (via `adb forward`). Set `LAMDA_HOST` or pass `--host` when the phone is on the LAN.

## Order of checks

1. `nc -vz "$LAMDA_HOST" 65000` from the new computer.
2. `curl -s -D - "http://$LAMDA_HOST:65000/"` — should return `Server: LAMDA/10.9`.
3. `python scripts/lamda_env_check.py --host "$LAMDA_HOST"`.
4. If Python fails but `nc` works, test `Device(...).server_info()` directly and read the exception.
5. Only after a successful screenshot/XML check should you write UI automation.

## Common causes

### Wrong address

- `127.0.0.1` means the computer itself, not the phone.
- `localhost` inside Docker means the container.
- Phone DHCP lease may have changed; confirm the LAN IP on the phone.

### Network isolation

- Client isolation / AP isolation blocks phone-to-PC traffic.
- Different VLAN/subnet without routing.
- Corporate firewall blocks TCP 65000.
- VPN split tunneling sends the phone IP outside the tunnel.

### LAMDA service

- Service not started or crashed.
- Shizuku not started after reboot.
- Port changed from 65000.
- TLS enabled but no certificate supplied.

### Computer permissions

- macOS Local Network permission can block Python but not `nc`.
- Windows Defender firewall may block outbound Python.
- Linux firewall/iptables/nftables may block outbound 65000.

### Screen state

- `is_screen_on() == False`: call `wake_up()` and wait.
- `is_screen_locked() == True`: unlock manually; a wake-up call will not dismiss a secure lock.
- A black screenshot with small bytes usually means screen off, lock screen, or a secure surface.

### Dependencies

- Activate the venv before `pip install`; otherwise the client installs elsewhere.
- `lamda` must match the server major/minor version where possible.
- If `grpcio` has no wheel, use Python 3.11/3.12 or install build tools.

## Minimal diagnostic

```python
from lamda.client import Device
d = Device("127.0.0.1", 65000)
print(d.server_info())
print(d.current_application())
print(d.is_screen_on(), d.is_screen_locked())
print(len(d.screenshot(80).getvalue()))
print(len(d.dump_window_hierarchy().getvalue()))
```
