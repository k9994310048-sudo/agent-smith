const base=process.env.BASE_URL || `http://127.0.0.1:${process.env.PORT || 9766}`;
const resp=await fetch(`${base}/v1/chat/completions`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${process.env.API_KEY || 'dummy'}`},body:JSON.stringify({model:process.env.MODEL || 'kimi-k2.5',messages:[{role:'user',content:'Reply exactly: FREEGLMKIMI_SMOKE_OK'}]})});
const json=await resp.json();
console.log(JSON.stringify(json,null,2));
if (!resp.ok) process.exit(1);
const text=json.choices?.[0]?.message?.content;
if (text !== 'FREEGLMKIMI_SMOKE_OK' && process.env.MOCK_PROVIDER==='1') process.exit(2);
