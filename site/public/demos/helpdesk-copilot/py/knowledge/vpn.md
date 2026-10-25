# VPN for remote work

The VPN connects your company laptop to the office network from home, from a hotel or from a
customer site. You need it for the file server (S: drive) and the accounting software.
Microsoft 365 (Outlook, Teams, OneDrive) works without VPN.

## Install the VPN client

The VPN client is **WireGuard**. It is preinstalled on company laptops. If it is missing,
install "WireGuard" from the Company Portal app. Your personal VPN profile is created by IT:
ask the IT desk for it, it arrives as a file named `name.surname.conf`. Import it in WireGuard
with **Add tunnel → Import from file**.

## Connect from home or while travelling

Open WireGuard and click **Activate** next to the "Sample Office" tunnel. The status turns
green and shows "Latest handshake" within a few seconds. Disconnect with **Deactivate** when
you no longer need office resources.

## VPN does not connect

- If there is no "Latest handshake", check that you have internet without the VPN first.
- Hotel and airport Wi-Fi often need you to accept their terms in the browser before anything
  else works: open any website, accept, then activate the tunnel again.
- Some public networks block VPN traffic. Use your phone as a hotspot instead.
- If it still fails, send the IT desk a screenshot of the WireGuard window. Never share the
  `.conf` file with anyone: it is your personal key.

## VPN is connected but the S: drive is missing

Open File Explorer and type `\\files.sample-office.local\shared` in the address bar. If that
works, the drive letter was only lost: sign out of Windows and in again to map it back.
