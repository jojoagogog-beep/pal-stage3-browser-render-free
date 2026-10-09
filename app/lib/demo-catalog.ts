import type {ProductInput} from "./product-audit";
const many=Array.from({length:24},(_,i)=>"tag"+(i+1));
export const demoProducts:ProductInput[]=[
{id:"p1",legacyResourceId:"9101",title:"Travel Starter Kit",handle:"travel-starter-kit",tags:[],status:"ACTIVE",updatedAt:"2024-04-10T10:00:00Z",images:{nodes:[{width:600,height:600},{width:1600,height:900}]},variants:{nodes:[{price:"0.00",compareAtPrice:"0.00"},{price:"40.00",compareAtPrice:"35.00"}]}},
{id:"p2",legacyResourceId:"9102",title:"Studio Carry Bag",handle:"studio-carry-bag",tags:["travel","bag"],status:"ACTIVE",updatedAt:"2026-09-01T10:00:00Z",images:{nodes:[{width:1600,height:900},{width:900,height:1600}]},variants:{nodes:[{price:"49.00",compareAtPrice:"49.00"},{price:"59.00",compareAtPrice:"79.00"}]}},
{id:"p3",legacyResourceId:"9103",title:"Seasonal Tee",handle:"seasonal-tee",tags:many,status:"DRAFT",updatedAt:"2023-03-01T10:00:00Z",images:{nodes:[{width:1200,height:1200},{width:1200,height:1200}]},variants:{nodes:[{price:"15.00",compareAtPrice:null},{price:"16.00",compareAtPrice:null}]}},
{id:"p4",legacyResourceId:"9104",title:"Studio Mug",handle:"studio-mug",tags:["home","ceramic"],status:"ACTIVE",updatedAt:"2026-09-20T10:00:00Z",images:{nodes:[{width:1200,height:1200},{width:1200,height:1200}]},variants:{nodes:[{price:"24.00",compareAtPrice:"29.00"},{price:"26.00",compareAtPrice:"31.00"}]}}
];
export const readyProducts:ProductInput[]=[demoProducts[3]];
