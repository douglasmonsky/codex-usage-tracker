import{c as i}from"./dashboardRouter.js";import{j as e}from"./dashboard-react.js";import{u as t}from"./App.js";/**
 * @license lucide-react v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const x=i("LockKeyhole",[["circle",{cx:"12",cy:"16",r:"1",key:"1au0dj"}],["rect",{x:"3",y:"10",width:"18",height:"12",rx:"2",key:"6s8ecr"}],["path",{d:"M7 10V7a5 5 0 0 1 10 0v3",key:"1pqi11"}]]);function m({title:a,subtitle:s,action:r,children:n,className:l=""}){const c=t();return e.jsxs("section",{className:`panel ${l}`.trim(),children:[e.jsxs("div",{className:"panel-header",children:[e.jsxs("div",{children:[e.jsx("h2",{children:c.translateText(a)}),s?e.jsx("p",{children:c.translateText(s)}):null]}),r?e.jsx("div",{className:"panel-action",children:r}):null]}),n]})}export{x as L,m as P};
