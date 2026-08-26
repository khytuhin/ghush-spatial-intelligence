import {escapeHtml as e,compact,taka,pct,METRICS,ratio,trendLabel,safeNumber} from './core.js';
const $=id=>document.getElementById(id);
const metricFormat=(key,value)=>METRICS[key]?.format(value)??compact(value);
const metricNames={report_count:'Reports',total_amount:'Amount',median_amount:'Median',refusal_rate:'Refusal'};
export function nationalMetric(state,dept=state.department){
  return state.week ? state.weekly.national[`${state.week}|${dept}`] : state.summary.slice_totals[`${state.period}|${dept}`];
}
export function divisionMetric(state,name,dept=state.department){
  return state.week ? state.weekly.divisions[name]?.[`${state.week}|${dept}`] : state.divisions.divisions.find(d=>d.name===name)?.slices[`${state.period}|${dept}`];
}
export function scopeMetric(state,dept=state.department){
  return state.division==='ALL'?nationalMetric(state,dept):divisionMetric(state,state.division,dept);
}
function bars(items,metric){
  const max=Math.max(1,...items.map(d=>safeNumber(d.metrics?.[metric])??0));
  return items.length?items.map(d=>{
    const v=safeNumber(d.metrics?.[metric]);
    return `<div class="bar-row"><div><span>${e(d.label)}</span><strong>${metricFormat(metric,v)}</strong></div><div class="bar-track"><i style="width:${v===null?0:Math.max(0,v/max*100)}%"></i></div></div>`;
  }).join(''):'<p class="empty-state">No published values.</p>';
}
function table(head,rows,caption){
  return `<table><caption>${e(caption)}</caption><thead><tr>${head.map(h=>`<th scope="col">${e(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`;
}
function spark(points,format,label){
  const finite=points.map(d=>d.value).filter(v=>safeNumber(v)!==null);
  if(!finite.length)return '<p class="empty-state">This metric is unavailable for the selected weeks.</p>';
  const W=560,H=195,L=54,R=24,T=24,B=36,max=Math.max(1,...finite);
  const x=i=>L+i*(W-L-R)/Math.max(1,points.length-1),y=v=>H-B-v/max*(H-T-B);
  let path='',open=false;
  points.forEach((p,i)=>{if(safeNumber(p.value)===null){open=false;return;}path+=(open?' L':' M')+x(i).toFixed(1)+','+y(p.value).toFixed(1);open=true;});
  const dots=points.filter(p=>safeNumber(p.value)!==null).map(p=>{
    const i=points.indexOf(p);return `<circle cx="${x(i)}" cy="${y(p.value)}" r="3"><title>${e(p.week)}: ${e(format(p.value))}</title></circle>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(label)}"><title>${e(label)}</title><path d="M${L} ${T}V${H-B}H${W-R}" class="axis"/><text x="4" y="${T+5}">${e(format(max))}</text><text x="4" y="${H-B+4}">0</text><path d="${path}" class="line"/>${dots}<text x="${L}" y="${H-8}">${e(points[0].week)}</text><text text-anchor="end" x="${W-R}" y="${H-8}">${e(points.at(-1).week)}</text></svg>`;
}
export function renderAnalytics(state){
  const period=state.week?'Week '+state.week:state.period==='ALL'?'All available':state.period;
  const context=`${state.division==='ALL'?'Bangladesh':state.division} · ${state.department==='ALL'?'All departments':state.department} · ${period}`;
  document.querySelectorAll('.analysis-context').forEach(el=>el.textContent=context);
  const national=nationalMetric(state);
  const all=state.divisions.divisions.map(d=>({...d,metrics:divisionMetric(state,d.name)}));
  const divs=state.division==='ALL'?all:all.filter(d=>d.name===state.division);
  const departments=(state.department==='ALL'?state.summary.departments:[state.department]).map(d=>({label:d,metrics:scopeMetric(state,d)}));
  const chartMetric=$('chartMetric').value;
  $('divisionTable').innerHTML=table(['Division','Reports','Reported amount','Median amount','Refusal','Per 100k','National share'],all.map(d=>{
    const m=d.metrics,share=national?.report_count>0?m?.report_count/national.report_count:null;
    return `<tr class="${d.name===state.division?'active-row':''}"><th scope="row"><button class="division-link" data-division="${e(d.name)}">${e(d.name)} ↗</button></th><td>${compact(m?.report_count)}</td><td>${taka(m?.total_amount)}</td><td>${taka(m?.median_amount)}</td><td>${pct(m?.refusal_rate)}</td><td>${METRICS.reports_per_100k.format(m?.reports_per_100k)}</td><td>${pct(share)}</td></tr>`;
  }),'Published reporting by division — '+period);
  $('departmentBars').innerHTML=bars(departments,chartMetric);
  const values=departments.flatMap(d=>divs.map(v=>safeNumber(divisionMetric(state,v.name,d.label)?.[chartMetric])??0));
  const max=Math.max(1,...values);
  $('departmentMatrix').innerHTML=table(['Department',...divs.map(v=>v.name)],departments.map(d=>`<tr><th scope="row">${e(d.label)}</th>${divs.map(v=>{
    const value=safeNumber(divisionMetric(state,v.name,d.label)?.[chartMetric]);
    return `<td class="heat-cell" style="background:rgba(48,104,129,${value===null?0:.06+.28*value/max})">${metricFormat(chartMetric,value)}</td>`;
  }).join('')}</tr>`),metricNames[chartMetric]+' by department and division');
  $('refusalDivisions').innerHTML=bars(divs.map(v=>({label:v.name,metrics:v.metrics})),'refusal_rate');
  $('refusalDepartments').innerHTML=bars(departments,'refusal_rate');
  const entity=state.division==='ALL'?state.summary:state.divisions.divisions.find(d=>d.name===state.division);
  const bands=state.week?null:entity.amount_bands[`${state.period}|${state.department}`];
  $('refusalBands').innerHTML=bands && !bands.every(b=>b.metrics.suppressed)
    ?bars(bands.map(b=>({label:b.band,metrics:b.metrics})),'refusal_rate')
    :'<p class="empty-state">'+(state.week?'Amount bands are available for rolling and all-time windows.':'Amount-band table withheld: underlying groups do not meet the privacy threshold.')+'</p>';
  const pop=state.summary.population;
  const bias=all.map(d=>{
    const reportShare=national?.report_count>0?d.metrics?.report_count/national.report_count:null;
    const populationShare=pop.available&&pop.total>0?d.population/pop.total:null;
    return {...d,reportShare,populationShare,representation:ratio(reportShare,populationShare)};
  });
  $('biasTable').innerHTML=table(['Division','Report share','Population share','Ratio'],bias.map(d=>`<tr><th scope="row">${e(d.name)}</th><td>${pct(d.reportShare)}</td><td>${pct(d.populationShare)}</td><td>${d.representation===null?'—':d.representation.toFixed(2)+'×'}</td></tr>`),'National representation, '+period);
  if(!pop.available || !national?.report_count){
    $('biasScatter').innerHTML='<p class="empty-state denominator-note">Population comparison unavailable. Supply a cited, complete population dataset matched to the boundary version. No estimates or synthetic denominators are substituted.</p>';
  } else {
    const maxShare=Math.max(.1,...bias.map(d=>Math.max(d.reportShare??0,d.populationShare??0)))*1.2;
    const x=v=>60+v/maxShare*360,y=v=>205-v/maxShare*165;
    $('biasScatter').innerHTML=`<svg viewBox="0 0 520 265" role="img" aria-label="Division report share versus population share"><title>Each point is one division; dashed diagonal means proportional representation</title><path class="axis" d="M60 40V205H420"/><path class="diagonal" d="M60 205L420 40"/>${bias.map(d=>`<circle cx="${x(d.populationShare)}" cy="${y(d.reportShare)}" r="4"><title>${e(d.name)}: ${d.representation.toFixed(2)}×</title></circle><text x="${x(d.populationShare)+6}" y="${y(d.reportShare)-5}">${e(d.name)}</text>`).join('')}<text x="60" y="225">0%</text><text x="390" y="225">${pct(maxShare)}</text><text x="150" y="250">Population share →</text><text x="12" y="25">Report share ↑</text></svg>`;
    $('biasScatter').insertAdjacentHTML('beforeend','<p class="fine-print">Denominator sources: '+pop.sources.map(e).join('; ')+'</p>');
  }
  const pulseMetric=$('pulseMetric').value;
  const series=state.division==='ALL'?state.weekly.national:state.weekly.divisions[state.division];
  const weeks=state.weekly.weeks.filter(w=>w<=state.weekly.complete_through);
  $('pulseContext').textContent=(state.division==='ALL'?'Bangladesh':state.division)+' / '+(state.department==='ALL'?'All departments':state.department)+' · Complete weeks; independent of rolling map window';
  $('pulseChart').innerHTML=spark(weeks.map(week=>({week,value:series[`${week}|${state.department}`]?.[pulseMetric]})),v=>metricFormat(pulseMetric,v),'Weekly '+metricNames[pulseMetric]);
  const trend=entity.trends[state.department];
  $('trendSummary').innerHTML=`<span class="trend-tag ${e(trend.category)}">${trendLabel(trend.category)}</span><span>${trend.change===null?'Not enough reports in both complete weeks.':(trend.change>0?'+':'')+pct(trend.change)+' vs previous complete week'}</span>`;
  const deptList=state.department==='ALL'?['ALL',...state.summary.departments]:[state.department];
  $('weeklyTable').innerHTML=table(['Week start','Department','Reports','Amount','Median','Refusal'],weeks.slice().reverse().flatMap(week=>deptList.map(dept=>{
    const m=series[`${week}|${dept}`];
    return `<tr><th scope="row">${week}</th><td>${e(dept==='ALL'?'All departments':dept)}</td><td>${compact(m?.report_count)}</td><td>${taka(m?.total_amount)}</td><td>${taka(m?.median_amount)}</td><td>${pct(m?.refusal_rate)}</td></tr>`;
  })),'Complete weekly aggregates; up to 52 weeks');
}
