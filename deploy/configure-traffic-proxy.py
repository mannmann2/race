#!/usr/bin/env python3
"""Add Race Atlas debug protection using the existing owner's debug-page login."""
import datetime,os,re,shutil,subprocess,tempfile
from pathlib import Path
path=Path('/etc/caddy/Caddyfile');source=path.read_text()
owner=re.search(r'^debug\.slopmaxx\.ing\s*\{(.*?)^\}',source,re.M|re.S)
credential=re.search(r'^\s*(arman)\s+(\$\S+)',owner[1] if owner else '',re.M)
if not credential:raise SystemExit('Existing owner debug credentials were not found; no proxy configuration changed.')
block=re.search(r'^race\.slopmaxx\.ing\s*\{.*?^\}',source,re.M|re.S)
if not block:raise SystemExit('Race proxy configuration was not found; no changes made.')
replacement='''race.slopmaxx.ing {
    @race_private path /debug*
    basicauth @race_private {
        %s %s
    }
    reverse_proxy 127.0.0.1:4173 {
        header_up X-Race-Client-IP {remote_host}
        header_up X-Race-Debug-User {http.auth.user.id}
    }
}''' % credential.groups()
updated=source[:block.start()]+replacement+source[block.end():]
if updated==source:print('Race traffic proxy is already configured.');raise SystemExit(0)
fd,name=tempfile.mkstemp(prefix='race-caddy-',suffix='.conf');os.chmod(name,0o600)
try:
 with os.fdopen(fd,'w') as file:file.write(updated)
 result=subprocess.run(['caddy','validate','--config',name,'--adapter','caddyfile'],capture_output=True,text=True)
 if result.returncode:raise SystemExit('Proxy validation failed; original configuration retained.\n'+result.stderr[-1500:])
 backup=path.with_name('Caddyfile.race-backup-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S'))
 shutil.copy2(path,backup);backup.chmod(0o600)
 path.write_text(updated)
 result=subprocess.run(['systemctl','reload','caddy'],capture_output=True,text=True)
 if result.returncode:
  shutil.copy2(backup,path);subprocess.run(['systemctl','reload','caddy'],check=False)
  raise SystemExit('Proxy reload failed; original configuration restored.')
 print('Protected /debug with the existing owner login; trusted client-IP headers are set by the proxy. Other sites are unchanged.')
finally:Path(name).unlink(missing_ok=True)
