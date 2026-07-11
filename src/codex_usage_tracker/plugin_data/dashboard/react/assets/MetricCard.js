import{j as e}from"./dashboard-react.js";import{G as d}from"./gauge.js";import{c as n,K as r,L as t}from"./App.js";/**
 * @license lucide-react v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const i=n("CircleDollarSign",[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8",key:"1h4pet"}],["path",{d:"M12 18V6",key:"zqpxq5"}]]);/**
 * @license lucide-react v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const h=n("PhoneCall",[["path",{d:"M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z",key:"foiqr5"}],["path",{d:"M14.05 2a9 9 0 0 1 8 7.94",key:"vmijpz"}],["path",{d:"M14.05 6A5 5 0 0 1 18 10",key:"13nbpp"}]]),m={"Cache Hit Rate":t,"Cache Reuse":t,"Estimated Cost":i,"Estimated Credits":i,"Total Calls":h,"Total Tokens":r,"Usage Remaining":d};function b({card:a}){var s;const c=m[a.label]??r,o=a.trend.startsWith("down")||a.trend.includes("risk")?"negative":"positive";return e.jsxs("article",{className:`metric-card metric-card-${a.tone}`,children:[e.jsx("div",{className:"metric-icon","aria-hidden":"true",children:e.jsx(c,{size:22})}),e.jsxs("div",{className:"metric-copy",children:[e.jsx("p",{children:a.label}),e.jsx("strong",{children:a.value}),(s=a.breakdown)!=null&&s.length?e.jsx("dl",{className:"metric-breakdown","aria-label":`${a.label} breakdown`,children:a.breakdown.map(l=>e.jsxs("div",{children:[e.jsx("dt",{children:l.label}),e.jsx("dd",{children:l.value})]},l.label))}):null,e.jsx("span",{className:`trend ${o}`,children:a.trend}),e.jsx("small",{children:a.detail})]})]})}export{b as M};
