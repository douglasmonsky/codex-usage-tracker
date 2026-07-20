import{j as t}from"./dashboard-react.js";import{c as i,u as p,F as h}from"./App.js";/**
 * @license lucide-react v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const u=i("ArrowRight",[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"m12 5 7 7-7 7",key:"xquz4c"}]]);/**
 * @license lucide-react v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const m=i("Waypoints",[["circle",{cx:"12",cy:"4.5",r:"2.5",key:"r5ysbb"}],["path",{d:"m10.2 6.3-3.9 3.9",key:"1nzqf6"}],["circle",{cx:"4.5",cy:"12",r:"2.5",key:"jydg6v"}],["path",{d:"M7 12h10",key:"b7w52i"}],["circle",{cx:"19.5",cy:"12",r:"2.5",key:"1piiel"}],["path",{d:"m13.8 17.7 3.9-3.9",key:"1wyg1y"}],["circle",{cx:"12",cy:"19.5",r:"2.5",key:"13o1pw"}]]),_="_root_caaoe_1",k="_icon_caaoe_18",j="_copy_caaoe_26",b="_action_caaoe_30",o={root:_,icon:k,copy:j,action:b};function w({kind:c,title:n,description:l,className:s,replacementAction:e}){const a=p(),y=c==="experimental"?h:m,d=s?`${o.root} ${s}`:o.root,r=a.translateText(n),x=a.translateText(l);return t.jsxs("aside",{"aria-label":a.formatText(a.t("maturity.aria","Feature maturity: {title}"),{title:r}),className:d,"data-kind":c,role:"note",children:[t.jsx(y,{"aria-hidden":"true",className:o.icon}),t.jsxs("div",{className:o.copy,children:[t.jsx("strong",{children:r}),t.jsx("p",{children:x})]}),e?t.jsxs("button",{className:o.action,type:"button",onClick:e.onSelect,children:[a.translateText(e.label),t.jsx(u,{"aria-hidden":"true"})]}):null]})}export{u as A,w as F};
