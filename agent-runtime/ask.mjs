import { Client } from 'eve/client';
try {
  let raw='';for await(const chunk of process.stdin)raw+=chunk;
  const input=JSON.parse(raw);const host=new URL(process.env.CH347_EVE_URL);
  if(!['127.0.0.1','localhost'].includes(host.hostname)||host.protocol!=='http:'||host.username||host.password)throw Error('Eve must be a loopback HTTP service');
  const client=new Client({host:host.origin,redirect:'error'});
  const {response}=await client.sessions.create({message:input.message});
  const result=await response.result();
  if(result.status!=='completed')throw Error('Agent did not complete: '+result.status);
  process.stdout.write(JSON.stringify({text:result.message||'模型未返回文本。'}));
}catch(e){process.stderr.write(e.message);process.exitCode=1;}
