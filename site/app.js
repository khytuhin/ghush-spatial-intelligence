import {safeNumber,getSlice,colorScale,validatePair,validateBundle,geometryBbox,escapeHtml,compact,taka,pct,METRICS,metricValue,trendLabel,csvFilename} from './core.js';
import {renderAnalytics,nationalMetric,scopeMetric} from './analytics.js';
const $=id=>document.getElementById(id);
const state={validated:false,summary:null,districts:null,adm3:null,divisions:null,weekly:null,metric:'report_count',department:'ALL',period:'ALL',division:'ALL',week:null,district:null,features:[],selected:null,map:null,ready:false};
let scale={stops:[],colors:[]},player=null,popup=null;
const periodLabel=p=>({ALL:'All available','30D':'Last 30 days','90D':'Last 90 days','365D':'Last 365 days'})[p]||p;
const notice=(message,error=false)=>{$('appNotice').textContent=message;$('appNotice').classList.toggle('error',error);$('appNotice').hidden=!message;};
async function fetchJson(path,optional=false){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try{const response=await fetch(path,{cache:'no-cache',signal:controller.signal});
    if(optional&&response.status===404)return null;
    if(!response.ok)throw new Error('Data request failed ('+response.status+').');
    return await response.json();
  }finally{clearTimeout(timer);}
}
async function load(){
  notice('Loading validated publication…');
  try{
    for(let attempt=0;attempt<2;attempt++){
      [state.districts,state.summary,state.divisions,state.weekly]=await Promise.all(['district_metrics.geojson','summary.json','division_summary.json','weekly_summary.json'].map(n=>fetchJson('./data/'+n)));
      try{validateBundle(state);break;}catch(error){if(attempt===1)throw error;}
    }
    $('departmentSelect').replaceChildren(...['ALL',...state.summary.departments].map(d=>new Option(d==='ALL'?'All departments':d,d)));
    $('periodSelect').replaceChildren(...state.summary.periods.map(p=>new Option(periodLabel(p),p)));
    $('divisionSelect').replaceChildren(new Option('All divisions','ALL'),...state.divisions.divisions.map(d=>new Option(d.name,d.name)));
    $('demoBanner').classList.toggle('hidden',!state.summary.meta.demo);
    $('dataMode').textContent=state.summary.meta.demo?'SYNTHETIC REPORTS / REAL BOUNDARIES':'PUBLISHED AGGREGATES';
    $('privacyValue').textContent=String(state.summary.meta.privacy_k);
    $('boundaryNote').textContent='2020 ADM2 / ADM3 · BBS, OCHA · CC BY 3.0 IGO';
    $('weekSlider').max=String(state.weekly.weeks.length-2);
    $('weekSlider').value=$('weekSlider').max;
    $('downloadCsv').href='./data/weekly_summary.csv';
    $('downloadCsv').download=csvFilename(state.weekly.complete_through);
    $('downloadCsv').setAttribute('aria-disabled','false');
    state.validated=true;
    document.querySelectorAll('.controls-grid select,.search-row button,.search-row input,#resetBtn,.timeline button,.timeline input,#chartMetric,#pulseMetric').forEach(el=>el.disabled=false);
    notice('');updateView();initMap();await freshness();
  }catch(error){
    notice('Publication unavailable or inconsistent. Retry to load a complete validated release; no fallback reports were substituted.',true);
    $('freshness').textContent='Data unavailable';$('retryBtn').hidden=false;console.error(error);
  }
}
function initMap(){
  try{
    if(!window.maplibregl)throw new Error('MapLibre is unavailable.');
    state.map=new maplibregl.Map({container:'map',center:[90.35,23.68],zoom:5.3,minZoom:4,maxZoom:12,attributionControl:false,
      style:{version:8,sources:{basemap:{type:'raster',tiles:['https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'],tileSize:256,
        attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> © <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>'}},
        layers:[{id:'background',type:'background',paint:{'background-color':'#e6e9e5'}},{id:'basemap',type:'raster',source:'basemap',paint:{'raster-opacity':.7}}]}});
    const map=state.map;
    map.addControl(new maplibregl.NavigationControl({showCompass:false}),'bottom-right');
    map.addControl(new maplibregl.AttributionControl({compact:true,customAttribution:'Boundaries: <a href="https://www.geoboundaries.org/" target="_blank" rel="noopener">geoBoundaries</a>'}),'bottom-left');
    map.on('error',event=>{$('mapStatus').textContent=event.sourceId==='basemap'?'Basemap unavailable · administrative data remains usable':'Map rendering problem · use search and the area list';if(event.sourceId!=='basemap')console.error(event.error);});
    map.once('load',()=>{
      map.addSource('areas',{type:'geojson',data:flatGeo(),promoteId:'shapeID'});
      map.addLayer({id:'areas-fill',type:'fill',source:'areas',paint:{'fill-color':'#356781','fill-opacity':.84}});
      map.addLayer({id:'areas-outline',type:'line',source:'areas',paint:{'line-color':'#fff','line-width':.8,'line-opacity':.8}});
      map.addLayer({id:'areas-selected',type:'line',source:'areas',filter:['==','shapeID',''],paint:{'line-color':'#bf4d2f','line-width':2.5}});
      state.ready=true;paint();fit();
      map.on('click','areas-fill',event=>selectArea(event.features?.[0]?.properties.shapeID));
      map.on('mousemove','areas-fill',event=>{
        map.getCanvas().style.cursor='pointer';
        const id=event.features?.[0]?.properties.shapeID,f=state.features.find(f=>f.properties.shapeID===id);
        if(!f)return;
        const p=f.properties,node=document.createElement('div');
        node.className='tooltip-text';node.textContent=p.shapeName+' · '+METRICS[state.metric].label+': '+METRICS[state.metric].format(p.selected_value)+(state.metric==='trend'?' ('+trendLabel(p.trend_category)+')':'');
        if(!popup)popup=new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:14});
        popup.setLngLat(event.lngLat).setDOMContent(node).addTo(map);
      });
      map.on('mouseleave','areas-fill',()=>{map.getCanvas().style.cursor='';popup?.remove();});
    });
    new ResizeObserver(()=>{map.resize();if(state.ready&&!state.selected)fit();}).observe($('map'));
  }catch(error){$('mapStatus').textContent='Interactive map unavailable. Search, area statistics and charts still work.';console.warn(error.message);}
}
function currentRaw(){
  return (state.district?state.adm3:state.districts).features.filter(f=>state.district?f.properties.districtID===state.district:state.division==='ALL'||f.properties.division===state.division);
}
function featureMetric(feature){
  return state.week?state.weekly.districts[feature.properties.shapeID]?.[`${state.week}|${state.department}`]??null:getSlice(feature,state.period,state.department);
}
function updateView(){
  if(!state.summary)return;
  const national=nationalMetric(state),raw=currentRaw();
  state.features=raw.map(f=>{
    const m=featureMetric(f),tr=state.week?null:f.properties.trends?.[state.department];
    return {type:'Feature',geometry:f.geometry,properties:{shapeID:f.properties.shapeID,shapeName:f.properties.shapeName,division:f.properties.division,
      ...m,selected_value:metricValue(state.metric,m,national,tr),trend_category:tr?.category??'insufficient'}};
  });
  const cfg=METRICS[state.metric],total=scopeMetric(state);
  scale=colorScale(state.features.map(f=>f.properties.selected_value),cfg.palette,cfg.divergent);
  $('activeLayerLabel').textContent=cfg.label;
  $('kpiReports').textContent=compact(total?.report_count);$('kpiAmount').textContent=taka(total?.total_amount);
  $('kpiMedian').textContent=taka(total?.median_amount);$('kpiRefusal').textContent=pct(total?.refusal_rate);
  const represented=state.districts.features.filter(f=>(state.division==='ALL'||f.properties.division===state.division)&&featureMetric(f)?.report_count>0).length;
  $('kpiDistricts').textContent=String(represented);
  $('kpiCoverage').textContent=(state.division==='ALL'?'Bangladesh':state.division)+' · '+(state.week?'Week '+state.week:periodLabel(state.period));
  $('viewContext').textContent=state.district?'District → Upazila detail':(state.division==='ALL'?'Bangladesh':state.division)+' / Districts';
  $('legend').innerHTML=scale.stops.length?`<div class="legend-bar" style="background:linear-gradient(to right,${scale.colors.join(',')})"></div><div class="legend-labels"><span>${cfg.format(scale.stops[0])}</span><span>${cfg.format(scale.stops.at(-1))}</span></div>`:'<span>No publishable values for this view</span>';
  $('legendNote').textContent=state.metric==='trend'?'Blue: declining · warm: rising · neutral: stable':'Muted: no value or privacy withheld';
  if(state.metric==='trend')$('legend').innerHTML='<div class="trend-legend"><span><i style="background:#3679a4"></i>Declining</span><span><i style="background:#b2b5ad"></i>Stable</span><span><i style="background:#ac4831"></i>Rising</span></div>';
  const rows=state.features.filter(f=>f.properties.selected_value!==null&&f.properties.report_count>0).sort((a,b)=>b.properties.selected_value-a.properties.selected_value).slice(0,10);
  $('rankTitle').textContent=cfg.label;
  $('rankList').innerHTML=rows.length?rows.map((f,i)=>`<button class="rank-item" type="button" data-id="${escapeHtml(f.properties.shapeID)}"><span class="rank-number">${String(i+1).padStart(2,'0')}</span><span class="rank-name"><strong>${escapeHtml(f.properties.shapeName)}</strong><small>${compact(f.properties.report_count)} reports${state.metric==='trend'?' · '+trendLabel(f.properties.trend_category):''}</small></span><span class="rank-value">${cfg.format(f.properties.selected_value)}</span></button>`).join(''):'<p class="empty-state">No values to rank. Try a different metric or filter.</p>';
  $('areaOptions').replaceChildren(...raw.map(f=>new Option(f.properties.shapeName)));
  const notes={
    total_amount:'Money concentration shows summed reported amounts by administrative area. It does not describe movement or money flows.',
    reports_per_100k:'Rates require complete, cited population data matching the boundary version. A dash means unavailable.',
    report_share:'Share of national published reports. Population, internet access, platform adoption and service exposure affect reporting; this is not corruption prevalence.',
    gi_z:'Exploratory Gi* on published counts; Queen adjacency, seed 42. No multiple-testing correction. Not proof of wrongdoing.',
    trend:'Last two complete weeks only, independent of the rolling window. Direction requires ≥10 reports in each week, ≥20% change and ≥k reports. Sparse areas have no trend.'
  };
  $('modeNote').textContent=notes[state.metric]||'All displayed statistics use the same publishable records. Empty or privacy-withheld values remain unavailable.';
  if(state.metric==='gi_z'&&!state.week){
    const stats=(state.district?state.summary.global_spatial:state.summary.district_global_spatial)[`${state.period}|${state.department}`];
    $('modeNote').textContent+=stats?` National ${state.district?'ADM3':'district'} Global Moran I: ${stats.moran_i.toFixed(3)}; permutation p: ${stats.p_sim.toFixed(3)} (${stats.permutations} permutations). Selecting a division does not recompute the national weights.`:' Global Moran is unavailable for this selection.';
  }
  if(state.week)$('modeNote').textContent+=' Weekly map: district level; amount-band and spatial/trend statistics are unavailable for a single week.';
  $('weekLabel').textContent=state.week||periodLabel(state.period);
  if(state.ready){state.map.getSource('areas').setData(flatGeo());paint();}
  if(state.selected)selectArea(state.selected,false,false);
  renderAnalytics(state);
}
function flatGeo(){return {type:'FeatureCollection',features:state.features};}
function paint(){
  const valid=['!=',['get','selected_value'],null];
  let expression=scale.expression;
  if(state.metric==='trend')expression=['match',['get','trend_category'],'rising','#ac4831','declining','#3679a4','stable','#b2b5ad','#d4d8d6'];
  state.map.setPaintProperty('areas-fill','fill-color',['case',valid,expression??'#d4d8d6','#aeb8b9']);
  state.map.setPaintProperty('areas-fill','fill-opacity',['case',valid,.84,.18]);
}
function selectArea(id,zoom=false,open=true){
  const f=state.features.find(f=>f.properties.shapeID===id);if(!f)return;
  state.selected=id;const p=f.properties;
  $('areaName').textContent=p.shapeName;
  $('areaSubtitle').textContent=p.division+' · '+(state.department==='ALL'?'All departments':state.department)+' · '+(state.week?'Week '+state.week:periodLabel(state.period));
  $('suppressionNote').hidden=!p.suppressed;
  const values=[['Published reports',compact(p.report_count)],['Reported amount',taka(p.total_amount)],['Median amount',taka(p.median_amount)],['Refusal rate',pct(p.refusal_rate)],['Per 100k',METRICS.reports_per_100k.format(p.reports_per_100k)],['Active map metric',METRICS[state.metric].format(p.selected_value)]];
  $('areaStats').innerHTML=values.map(([k,v])=>`<div><span>${escapeHtml(k)}</span><strong>${escapeHtml(v)}</strong></div>`).join('');
  $('clusterCard').textContent=p.gi_z==null?'Spatial statistics unavailable for this selection.':`Gi*: ${p.gi_z.toFixed(2)} · permutation p: ${p.gi_p?.toFixed(3)??'—'} · Local Moran: ${p.moran_cluster??'no significant label'}. Exploratory only.`;
  $('drillBtn').hidden=Boolean(state.district)||Boolean(state.week);
  $('drillBtn').disabled=!p.report_count;
  if(open){$('inspector').hidden=false;$('closeInspector').focus({preventScroll:true});}
  if(state.ready){
    state.map.setFilter('areas-selected',['==','shapeID',id]);
    if(zoom){const b=geometryBbox(f.geometry);if(b)state.map.fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:65,maxZoom:9,duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:400});}
  }
}
function fit(){
  if(!state.ready)return;
  const boxes=state.features.map(f=>geometryBbox(f.geometry)).filter(Boolean);if(!boxes.length)return;
  state.map.fitBounds([[Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1]))],[Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))]],{padding:32,duration:0,maxZoom:9});
}
function closeInspector(){state.selected=null;$('inspector').hidden=true;popup?.remove();if(state.ready)state.map.setFilter('areas-selected',['==','shapeID','']);}
function search(){
  const q=$('areaSearch').value.trim().toLocaleLowerCase();if(!q)return;
  const matches=state.features.filter(f=>f.properties.shapeName.toLocaleLowerCase().includes(q));
  if(matches.length===1){selectArea(matches[0].properties.shapeID,true);$('searchFeedback').textContent='';}
  else $('searchFeedback').textContent=matches.length?'Multiple areas match. Enter the full name.':'No matching area in the current geography.';
}
async function drill(){
  if(!state.selected||state.week)return;
  const target=state.selected;
  try{
    $('drillBtn').disabled=true;
    if(!state.adm3){const geo=await fetchJson('./data/adm3_metrics.geojson');validatePair(geo,state.summary);state.adm3=geo;}
    if(state.selected!==target||state.week)return;
    state.district=target;closeInspector();updateView();fit();
  }catch(error){notice('Upazila detail could not be loaded from this release. The district map remains available. Please reload to retry.',true);console.error(error);}
  finally{$('drillBtn').disabled=false;}
}
async function freshness(){
  const meta=state.summary.meta;let heartbeat=null;
  if(!meta.demo){try{heartbeat=await fetchJson('./data/refresh.json',true);}catch{/* Optional status never invalidates published data. */}}
  const checked=new Date(heartbeat?.checked_at),valid=Number.isFinite(checked.getTime())&&checked.getTime()<=Date.now()+300000;
  const verified=!meta.demo&&heartbeat?.status==='ok'&&heartbeat.data_id===meta.data_id&&valid;
  const date=new Date(verified?heartbeat.checked_at:meta.generated_at);
  $('freshness').textContent=meta.demo?'SYNTHETIC / NOT LIVE':verified?'SOURCE CHECKED '+date.toLocaleString():'SNAPSHOT / NO VERIFIED REFRESH';
  $('kpiRefresh').textContent=verified?date.toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):meta.demo?'DEMO':'UNVERIFIED';
  $('refreshDetail').textContent=verified?'UTC '+checked.toISOString().slice(0,16).replace('T',' '):'Publication: '+date.toISOString().slice(0,10);
  if(!meta.demo&&(!verified||Date.now()-date.getTime()>36*3600000))notice('Showing the last validated publication. A recent successful source refresh has not been verified.');
}
function stop(){if(player)clearInterval(player);player=null;$('playBtn').textContent='▶ Play';$('playBtn').setAttribute('aria-label','Play weekly map');}
function setWeek(index){state.district=null;state.week=state.weekly.weeks[index];closeInspector();updateView();}
for(const [id,key] of [['metricSelect','metric'],['departmentSelect','department'],['periodSelect','period'],['divisionSelect','division']]){
  $(id).addEventListener('change',event=>{
    stop();state[key]=event.target.value;
    if(key==='period'){state.week=null;}
    if(key==='division'){state.district=null;closeInspector();}
    updateView();if(key==='division')fit();
  });
}
$('weekSlider').addEventListener('input',event=>{stop();setWeek(Number(event.target.value));});
$('playBtn').addEventListener('click',()=>{
  if(player){stop();return;}
  const advance=()=>{const max=Number($('weekSlider').max),next=state.week?(Number($('weekSlider').value)+1)%(max+1):0;$('weekSlider').value=String(next);setWeek(next);};
  advance();player=setInterval(advance,1600);$('playBtn').textContent='Ⅱ Pause';$('playBtn').setAttribute('aria-label','Pause weekly map');
});
$('allTimeBtn').addEventListener('click',()=>{stop();state.week=null;updateView();});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
window.addEventListener('pagehide',stop);
$('chartMetric').addEventListener('change',()=>{if(state.validated)renderAnalytics(state);});
$('pulseMetric').addEventListener('change',()=>{if(state.validated)renderAnalytics(state);});
$('divisionTable').addEventListener('click',event=>{
  const button=event.target.closest('[data-division]');if(!button)return;
  state.division=button.dataset.division;state.district=null;$('divisionSelect').value=state.division;closeInspector();updateView();fit();
});
$('rankList').addEventListener('click',event=>{const button=event.target.closest('[data-id]');if(button)selectArea(button.dataset.id,true);});
$('drillBtn').addEventListener('click',drill);
$('searchBtn').addEventListener('click',search);$('areaSearch').addEventListener('keydown',event=>{if(event.key==='Enter')search();});
$('resetBtn').addEventListener('click',()=>{state.district=null;state.division='ALL';$('divisionSelect').value='ALL';$('areaSearch').value='';closeInspector();updateView();fit();});
$('closeInspector').addEventListener('click',()=>{closeInspector();$('areaSearch').focus({preventScroll:true});});
$('methodBtn').addEventListener('click',()=>$('methodDialog').showModal());$('closeMethod').addEventListener('click',()=>$('methodDialog').close());
$('methodDialog').addEventListener('click',event=>{if(event.target===$('methodDialog'))$('methodDialog').close();});
$('retryBtn').addEventListener('click',()=>location.reload());document.addEventListener('keydown',event=>{if(event.key==='Escape')closeInspector();});
load();
