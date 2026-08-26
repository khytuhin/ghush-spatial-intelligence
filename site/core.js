// Pure presentation helpers; tested with Node's built-in test runner.
export function safeNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
export function getSlice(feature, period, department) {
  // A missing filter is missing, never a different department or time window.
  return feature.properties.slices[`${period}|${department}`] ?? null;
}
export function colorScale(values, palette, divergent = false) {
  const sorted = values.filter(v => safeNumber(v) !== null).sort((a,b) => a-b);
  if (!sorted.length) return { stops: [], colors: [], expression: '#242b32' };
  if(!divergent && sorted[0]===sorted.at(-1)){
    const color=sorted[0]===0?palette[0]:palette[Math.floor(palette.length/2)];
    return {stops:[sorted[0]],colors:[color],expression:color};
  }
  let stops, colors;
  if (divergent) {
    const max = Math.max(1, ...sorted.map(Math.abs));
    stops = [-max, -max/2, 0, max/2, max]; colors = palette;
  } else {
    const entries = palette.map((color, i) => {
      const p = (sorted.length-1)*i/(palette.length-1), lo=Math.floor(p), hi=Math.ceil(p);
      return [sorted[lo]+(sorted[hi]-sorted[lo])*(p-lo), color];
    });
    // MapLibre interpolation inputs must be strictly increasing.
    const unique = [...new Map(entries).entries()];
    stops = unique.map(x=>x[0]); colors = unique.map(x=>x[1]);
  }
  const expression = stops.length === 1 ? colors[0] :
    ['interpolate', ['linear'], ['get', 'selected_value'], ...stops.flatMap((x,i)=>[x,colors[i]])];
  return {stops, colors, expression};
}
export function validatePair(geo, summary) {
  if (geo?.type !== 'FeatureCollection' || !geo.features?.length ||
      ![2,3].includes(geo.schema_version) || summary?.meta?.schema_version !== geo.schema_version ||
      !geo.data_id || geo.data_id !== summary.meta.data_id ||
      !Array.isArray(summary.departments) || !Array.isArray(summary.periods) ||
      !summary.slice_totals?.['ALL|ALL']) throw new Error('Data files are incomplete or belong to different releases.');
  const keys = summary.periods.flatMap(p=>['ALL',...summary.departments].map(d=>`${p}|${d}`));
  const ids = new Set();
  for (const f of geo.features) {
    if (!['Polygon','MultiPolygon'].includes(f.geometry?.type) || !f.properties?.shapeID ||
        ids.has(f.properties.shapeID) || !f.properties.slices ||
        keys.some(k=>!f.properties.slices[k])) throw new Error('Invalid administrative map data.');
    ids.add(f.properties.shapeID);
    for (const m of Object.values(f.properties.slices)) {
      if (m.suppressed && Object.entries(m).some(([k,v])=>k!=='suppressed' && v!==null))
        throw new Error('Privacy validation failed.');
    }
  }
}
export function geometryBbox(geometry) {
  let box = [Infinity, Infinity, -Infinity, -Infinity];
  const walk = node => {
    if (Array.isArray(node) && typeof node[0] === 'number') {
      box = [Math.min(box[0],node[0]),Math.min(box[1],node[1]),Math.max(box[2],node[0]),Math.max(box[3],node[1])];
    } else if (Array.isArray(node)) node.forEach(walk);
  };
  walk(geometry?.coordinates);
  return box.every(Number.isFinite) ? box : null;
}
export function escapeHtml(value='') {
  return String(value).replace(/[&<>'"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

export const compact = v => safeNumber(v) === null ? '—' : new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(v);
export const taka = v => safeNumber(v) === null ? '—' : '৳'+compact(v);
export const pct = v => safeNumber(v) === null ? '—' : new Intl.NumberFormat('en',{style:'percent',maximumFractionDigits:1}).format(v);
const blue=['#d8e2e9','#a3bdce','#698ea8','#366782','#123f59'];
export const METRICS={
  report_count:{label:'Report activity',format:compact,palette:blue},
  total_amount:{label:'Money concentration',format:taka,palette:['#f4e2b7','#e5bd75','#cb9341','#a56c28','#704215']},
  median_amount:{label:'Median reported amount',format:taka,palette:blue},
  refusal_rate:{label:'Refusal rate',format:pct,palette:blue},
  reports_per_100k:{label:'Reports per 100k people',format:v=>safeNumber(v)===null?'—':v.toFixed(1),palette:blue},
  report_share:{label:'Reporting concentration',format:pct,palette:blue},
  gi_z:{label:'Exploratory hotspot · Gi*',format:v=>safeNumber(v)===null?'—':v.toFixed(2),palette:['#3679a4','#92b5cb','#ebe9e1','#d7a083','#ac4831'],divergent:true},
  trend:{label:'Weekly report trend',format:v=>safeNumber(v)===null?'Insufficient':(v>0?'+':'')+pct(v),palette:['#3679a4','#92b5cb','#ebe9e1','#d7a083','#ac4831'],divergent:true}
};
export function ratio(reportShare,populationShare){
  return safeNumber(reportShare)!==null && safeNumber(populationShare)!==null && populationShare>0 ? reportShare/populationShare : null;
}
export function metricValue(metric,m,total,trend=null){
  if(!m || m.suppressed || safeNumber(m.report_count)===null) return null;
  if(metric==='report_share') return total?.report_count>0?m.report_count/total.report_count:null;
  if(metric==='trend') return safeNumber(trend?.change);
  return safeNumber(m[metric]);
}
export function trendLabel(value){return ({rising:'Rising',declining:'Declining',stable:'Stable',insufficient:'Insufficient data'})[value]||'Insufficient data';}
export function csvFilename(week){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(week)) throw new Error('Invalid weekly export date.');
  return `ghush_spatial_weekly_${week}.csv`;
}
export function validateBundle(bundle){
  const {adm3,districts,summary,divisions,weekly}=bundle;
  if(adm3)validatePair(adm3,summary);validatePair(districts,summary);
  if(summary.meta.schema_version!==3 || divisions?.schema_version!==3 || weekly?.schema_version!==3 ||
     divisions.data_id!==summary.meta.data_id || weekly.data_id!==summary.meta.data_id ||
     divisions.divisions?.length!==8 || !Array.isArray(weekly.weeks) || weekly.weeks.length<3)
    throw new Error('Data files are incomplete or belong to different releases.');
  const districtIds=new Set(districts.features.map(f=>f.properties.shapeID));
  if(adm3?.features.some(f=>!districtIds.has(f.properties.districtID)))throw new Error('Invalid geographic parent links.');
  const check=m=>{
    if(!m || typeof m.suppressed!=='boolean')throw new Error('Invalid aggregate.');
    if(m.suppressed){if(Object.entries(m).some(([k,v])=>k!=='suppressed'&&v!==null))throw new Error('Privacy validation failed.');}
    else if(!Number.isInteger(m.report_count)||m.report_count<0||(m.report_count>0&&m.report_count<summary.meta.privacy_k))throw new Error('Privacy validation failed.');
    for(const [k,v] of Object.entries(m))if(!['suppressed','moran_cluster'].includes(k)&&v!==null&&safeNumber(v)===null)throw new Error('Invalid numeric metric.');
  };
  for(const geo of [adm3,districts].filter(Boolean))for(const f of geo.features)Object.values(f.properties.slices).forEach(check);
  for(const d of divisions.divisions)Object.values(d.slices).forEach(check);
  for(const series of [weekly.national,...Object.values(weekly.divisions),...Object.values(weekly.districts)])Object.values(series).forEach(check);
}
