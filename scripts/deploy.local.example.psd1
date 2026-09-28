# Copy to deploy.local.psd1 (same folder) and fill in. That copy is gitignored:
# the VM's address stays out of git, and is handed over with the SSH key.
@{
    # The VM's public IP (the same VM as Reels).
    VmHost  = "203.0.113.10"
    # Taskly's DuckDNS host name, as in ~/proxy/Caddyfile on the VM.
    Site    = "taskly-example.duckdns.org"
    # The private SSH key. ~ means your Windows home folder.
    KeyFile = "~\.ssh\reels_oci"
    User    = "ubuntu"
}
