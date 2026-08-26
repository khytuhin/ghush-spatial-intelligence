import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {colorScale,safeNumber,getSlice,validatePair,geometryBbox,escapeHtml} from '../site/core.js';
import {validateBundle,ratio,metricValue,trendLabel,csvFilename,METRICS} from '../site/core.js';
const colors=['#000000','#333333','#666666','#999999','#ffffff'];
test('duplicate quantiles always have strictly increasing stops',()=>{
  for(const values of [[0,0,0,1,1],[0,0,0,0],[5],[1,2,3],[]]) {
    const scale=colorScale(values,colors);
    assert.ok(scale.stops.every((s,i)=>i===0||s>scale.stops[i-1]));
  }
});
test('missing filter does not fall back to ALL',()=>{
  assert.equal(getSlice({properties:{slices:{'ALL|ALL':{report_count:500}}}},'30D','BRTA'),null);
});
test('null, strings and infinite values are never rendered as counts',()=>{
  for(const v of [null,undefined,NaN,Infinity,'12',''])assert.equal(safeNumber(v),null);
  assert.equal(safeNumber(0),0);
});
test('divergent scale is symmetric',()=>{
  assert.deepEqual(colorScale([1,4],colors,true).stops,[-4,-2,0,2,4]);
});
test('polygon bounds support multipolygon nesting',()=>{
  assert.deepEqual(geometryBbox({coordinates:[[[[89,23],[91,24],[89,23]]]]}),[89,23,91,24]);
});
test('escape untrusted labels',()=>assert.equal(escapeHtml('<script>"'), '&lt;script&gt;&quot;'));
test('bundled public pair and all filter combinations are valid',()=>{
  const geo=JSON.parse(fs.readFileSync(new URL('../site/data/adm3_metrics.geojson',import.meta.url)));
  const summary=JSON.parse(fs.readFileSync(new URL('../site/data/summary.json',import.meta.url)));
  validatePair(geo,summary);
  for(const feature of geo.features)for(const p of summary.periods)for(const d of ['ALL',...summary.departments])
    assert.ok(getSlice(feature,p,d));
  summary.meta.data_id='mismatch';
  assert.throws(()=>validatePair(geo,summary),/different releases/);
});

const read=name=>JSON.parse(fs.readFileSync(new URL('../site/data/'+name,import.meta.url)));
const bundle=()=>({adm3:read('adm3_metrics.geojson'),districts:read('district_metrics.geojson'),summary:read('summary.json'),divisions:read('division_summary.json'),weekly:read('weekly_summary.json')});
test('schema 3 whole bundle and lazy district overview validate',()=>{
  const b=bundle();validateBundle(b);delete b.adm3;validateBundle(b);
  b.weekly.data_id='different';assert.throws(()=>validateBundle(b),/different releases/);
});
test('all eight map modes preserve nulls and use the chosen metric',()=>{
  assert.equal(Object.keys(METRICS).length,8);
  for(const metric of Object.keys(METRICS))assert.equal(metricValue(metric,{suppressed:true,report_count:null},{}),null);
  assert.equal(metricValue('report_share',{report_count:25},{report_count:100}),.25);
  assert.equal(metricValue('total_amount',{report_count:5,total_amount:1200},{report_count:5}),1200);
  assert.equal(metricValue('trend',{report_count:10},{report_count:10},{change:null}),null);
  assert.equal(metricValue('trend',{report_count:10},{report_count:10},{change:-.5}),-.5);
  assert.equal(metricValue('report_count',{report_count:0},{report_count:10}),0);
  assert.equal(metricValue('report_share',{report_count:0},{report_count:10}),0);
  assert.equal(metricValue('gi_z',{report_count:0,gi_z:-1.5},{report_count:10}),-1.5);
  assert.equal(colorScale([0,0],colors).expression,colors[0]);
});
test('bias ratio interpretation and missing denominator',()=>{
  assert.equal(ratio(.2,.1),2);assert.equal(ratio(.1,.2),.5);assert.equal(ratio(.1,.1),1);
  for(const p of [null,undefined,0,NaN])assert.equal(ratio(.2,p),null);
});
test('CSV has a dated safe filename and no manual report fields',()=>{
  assert.equal(csvFilename('2026-08-17'),'ghush_spatial_weekly_2026-08-17.csv');
  assert.throws(()=>csvFilename('../private'));
  const header=fs.readFileSync(new URL('../site/data/weekly_summary.csv',import.meta.url),'utf8').split('\n')[0];
  assert.equal(header,'week_start,division,district,department,published_reports,reported_amount,median_amount,refusal_rate');
});
test('sparse trend is explicit and labels are never proof of corruption',()=>{
  assert.equal(trendLabel('insufficient'),'Insufficient data');assert.equal(trendLabel('rising'),'Rising');
});
test('shared filter matrix is complete for every district, division and week',()=>{
  const b=bundle();
  for(const d of b.divisions.divisions)for(const p of b.summary.periods)for(const dept of ['ALL',...b.summary.departments])assert.ok(d.slices[`${p}|${dept}`]);
  for(const f of b.districts.features)for(const w of b.weekly.weeks)for(const dept of ['ALL',...b.summary.departments])assert.ok(b.weekly.districts[f.properties.shapeID][`${w}|${dept}`]);
});
