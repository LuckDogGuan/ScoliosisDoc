// Graph stays in the existing Windows cache; every Git read executes in authoritative WSL.
import cp from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
import { LocalBackend } from 'file:///C:/Users/31186/AppData/Roaming/npm/node_modules/gitnexus/dist/mcp/local/local-backend.js';
const nativeExec = cp.execFileSync;
cp.execFileSync = (command, args, options) => command === 'git'
  ? nativeExec('wsl.exe', ['-d','Luckfox-Ubuntu-22.04','-e','git','-C','/home/guanjx/luckfox/Scoliosis',...args], {...options, cwd:'D:/code/Scoliosis/Luckfox'})
  : nativeExec(command,args,options);
syncBuiltinESMExports();
const backend = new LocalBackend();
await backend.init();
try {
  const result = await backend.callTool('detect_changes',{repo:process.argv[3] || 'scoliosis-firmware-index-20261008',scope:process.argv[2] || 'all'});
  console.log(JSON.stringify(result,null,2));
  if (result.error) process.exitCode=1;
} finally { await backend.dispose(); }
