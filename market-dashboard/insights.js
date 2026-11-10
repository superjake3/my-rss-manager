const HISTORY_URL = "./data/market-history.json";
const nf = (n, d=2) => Number.isFinite(Number(n)) ? new Intl.NumberFormat("ko-KR",{maximumFractionDigits:d,minimumFractionDigits:d}).format(Number(n)) : "—";
const pct = n => Number.isFinite(n) ? (n>0?"+":"")+n.toFixed(2)+"%" : "—";
const money = n => Number.isFinite(n) ? nf(n,0)+"원" : "—";
const changePct = (a,b) => Number.isFinite(a)&&Number.isFinite(b)&&b!==0 ? (a/b-1)*100 : null;
const el = id => document.getElementById(id);
let historyRows = [];
function periodChange(key, days) {
  if (!historyRows.length) return null;
  const latest = historyRows[historyRows.length-1], target = historyRows[Math.max(0, historyRows.length-1-days)];
  if (!latest || !target || latest[key] == null || target[key] == null) return null;
  return changePct(Number(latest[key]), Number(target[key]));
}
function renderPeriod(id, value) {
  const node=el(id); if(!node)return;
  node.textContent=pct(value); node.className="insight-change "+(value>0?"up":value<0?"down":"flat");
}
function renderHistoryChart() {
  const svg=el("historyChart"); if(!svg)return;
  const rows=historyRows.filter(r=>Number.isFinite(Number(r.krx_krw_g))).slice(-30);
  if(rows.length<2){svg.innerHTML='<text x="360" y="105" fill="#9aa99e" text-anchor="middle" font-size="13">KRX 일별 데이터가 쌓이면 30일 추이를 보여줍니다.</text>';return;}
  const vals=rows.map(r=>Number(r.krx_krw_g)),min=Math.min(...vals),max=Math.max(...vals),span=max-min||1;
  const x=i=>26+i/(rows.length-1)*668,y=v=>180-(v-min)/span*140;
  const path=vals.map((v,i)=>(i?"L":"M")+x(i).toFixed(1)+","+y(v).toFixed(1)).join(" ");
  const area=path+" L "+x(vals.length-1)+",190 L 26,190 Z";
  svg.innerHTML='<defs><linearGradient id="historyFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#b9a0d8" stop-opacity=".3"/><stop offset="1" stop-color="#b9a0d8" stop-opacity="0"/></linearGradient></defs><line x1="26" y1="40" x2="694" y2="40" stroke="#2b3a30"/><line x1="26" y1="110" x2="694" y2="110" stroke="#2b3a30"/><line x1="26" y1="190" x2="694" y2="190" stroke="#2b3a30"/><path d="'+area+'" fill="url(#historyFill)"/><path d="'+path+'" fill="none" stroke="#b9a0d8" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><text x="26" y="20" fill="#9aa99e" font-size="11">'+nf(max,0)+'원</text><text x="694" y="20" fill="#9aa99e" font-size="11" text-anchor="end">'+nf(min,0)+'원</text><text x="26" y="210" fill="#9aa99e" font-size="10">'+rows[0].base_date+'</text><text x="694" y="210" fill="#9aa99e" font-size="10" text-anchor="end">'+rows[rows.length-1].base_date+'</text>';
}
function renderDailyLesson() {
  const box=el("dailyLesson"); if(!box)return;
  if(historyRows.length<2){box.textContent="서로 다른 거래일의 데이터가 2개 이상 쌓이면 국제 금과 환율이 국내 금 가격에 미친 영향을 비교해 드립니다.";return;}
  const a=historyRows[historyRows.length-2],b=historyRows[historyRows.length-1];
  const g=changePct(Number(b.gold_usd_oz),Number(a.gold_usd_oz)),f=changePct(Number(b.usdkrw),Number(a.usdkrw));
  const k=changePct(Number(b.krx_krw_g),Number(a.krx_krw_g)),s=changePct(Number(b.spot_krw_g),Number(a.spot_krw_g));
  const gapA=Number(a.krx_krw_g)-Number(a.spot_krw_g),gapB=Number(b.krx_krw_g)-Number(b.spot_krw_g);
  const gapMove=Number.isFinite(gapA)&&Number.isFinite(gapB)?gapB-gapA:null,lines=[];
  if(g!==null&&f!==null){
    if(g*f<0) lines.push("국제 금과 환율이 반대 방향으로 움직여 서로의 영향을 일부 상쇄했습니다.");
    else if(Math.abs(g)>Math.abs(f)) lines.push("원화 기준 국제 금 가격 변화에서는 국제 금 가격의 움직임이 환율보다 크게 작용했습니다.");
    else lines.push("원화 기준 국제 금 가격 변화에서는 환율의 움직임이 국제 금 가격보다 크게 작용했습니다.");
  } else lines.push("국제 금 또는 환율의 비교 데이터가 부족해 요인 분석을 보류합니다.");
  if(k!==null&&s!==null){
    const residual=k-s; lines.push("KRX 금 가격 "+pct(k)+", 국제 환산 기준가 "+pct(s)+"로 움직였습니다.");
    if(Math.abs(residual)>0.15) lines.push("두 변화의 차이는 약 "+pct(residual)+"p입니다. 국내 수급·기준 시각 차이·시장 구조의 영향을 추가로 살펴볼 만합니다.");
    else lines.push("두 가격의 일간 움직임은 대체로 비슷했습니다.");
  } else lines.push("KRX 종가와 국제 환산가의 일간 비교는 데이터가 더 쌓인 뒤 가능합니다.");
  if(gapMove!==null) lines.push("국내 가격 차이는 전일 대비 "+money(gapMove)+" 변화했습니다.");
  box.innerHTML=lines.map(t=>'<p>'+t+'</p>').join("");
}
async function loadMarketHistory(){
  try{const response=await fetch(HISTORY_URL+"?v="+Date.now(),{cache:"no-store"});if(!response.ok)throw Error("history not ready");const data=await response.json();historyRows=Array.isArray(data.records)?data.records:[];}catch(e){historyRows=[];}
  renderPeriod("krx7d",periodChange("krx_krw_g",7));renderPeriod("krx30d",periodChange("krx_krw_g",30));
  renderPeriod("spot7d",periodChange("spot_krw_g",7));renderPeriod("fx7d",periodChange("usdkrw",7));
  if(el("historyCount"))el("historyCount").textContent=historyRows.length+"거래일 축적";
  if(el("historyLatest"))el("historyLatest").textContent=historyRows.length?historyRows[historyRows.length-1].base_date+" 기준":"데이터 대기 중";
  renderHistoryChart();renderDailyLesson();
}
document.addEventListener("DOMContentLoaded",loadMarketHistory);
