import test from "node:test";
import assert from "node:assert/strict";
import {probeConnection} from "../../apps/desktop/src/probeConnection.ts";

for(const probeFails of [false,true]) for(const failure of ["refresh","onSaved"]) {
  test(`probe ${probeFails?"fails":"succeeds"}, ${failure} rejects`,async()=>{
    const busy:boolean[]=[],errors:string[]=[],calls:string[]=[];
    await probeConnection({
      probe:async()=>{calls.push("probe");if(probeFails)throw Error("probe-error");return {models:[]};},
      refresh:async()=>{calls.push("refresh");if(failure==="refresh")throw Error("refresh-error");},
      onSaved:async()=>{calls.push("onSaved");if(failure==="onSaved")throw Error("callback-error");},
      alive:()=>true,busy:value=>busy.push(value),success:()=>calls.push("success"),
      error:value=>errors.push(value),message:error=>(error as Error).message,
    });
    assert.deepEqual(busy,[true,false]);
    assert.match(errors.at(-1)!,failure==="refresh"?/refresh-error/:/callback-error/);
    if(probeFails)assert.match(errors.at(-1)!,/probe-error/);
  });
}

test("unmount before probe resolves prevents all subsequent state/callback effects",async()=>{
  let alive=true,resolve!:(value:number)=>void;
  const busy:boolean[]=[],effects:string[]=[];
  const pending=probeConnection({probe:()=>new Promise<number>(done=>{resolve=done;}),
    refresh:async()=>{effects.push("refresh");},onSaved:async()=>{effects.push("onSaved");},
    alive:()=>alive,busy:value=>busy.push(value),success:()=>effects.push("success"),error:()=>{},message:String});
  alive=false;resolve(1);await pending;
  assert.deepEqual(effects,[]);assert.deepEqual(busy,[true]);
});
