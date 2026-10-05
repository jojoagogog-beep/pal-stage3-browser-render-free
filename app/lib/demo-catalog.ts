import type {ProductInput} from "./product-audit";
export const demoProducts:ProductInput[]=[
{id:"p1",legacyResourceId:"7101",title:"SUMMER BAG",handle:"summer-bag",status:"ACTIVE",updatedAt:"2026-09-25T00:00:00Z",descriptionHtml:"<p>A compact summer bag with an adjustable strap and interior pocket for daily use.</p>",images:{nodes:[{altText:null},{altText:"Summer bag front"}]},media:{nodes:[{mediaContentType:"IMAGE"}]}},
{id:"p2",legacyResourceId:"7102",title:"Cap",handle:"cap",status:"DRAFT",updatedAt:"2026-05-01T00:00:00Z",descriptionHtml:"",images:{nodes:[{altText:"Black cap"},{altText:"Black cap"}]},media:{nodes:[]}},
{id:"p3",legacyResourceId:"7103",title:"Travel Organizer Pouch with Multiple Compartments and Water Resistant Exterior",handle:"travel-organizer",status:"ACTIVE",updatedAt:"2026-09-28T00:00:00Z",descriptionHtml:"<p>Travel organizer.</p>",images:{nodes:[{altText:"Travel organizer"}]},media:{nodes:[{mediaContentType:"IMAGE"},{mediaContentType:"VIDEO"}]}},
{id:"p4",legacyResourceId:"7104",title:"Studio Mug",handle:"studio-mug",status:"ACTIVE",updatedAt:"2026-09-30T00:00:00Z",descriptionHtml:"<p>A durable ceramic studio mug designed for everyday hot and cold drinks with a comfortable handle and clean finish.</p>",images:{nodes:[{altText:"Studio mug front"},{altText:"Studio mug side"}]},media:{nodes:[{mediaContentType:"IMAGE"},{mediaContentType:"IMAGE"}]}}
];
export const readyProducts:ProductInput[]=[demoProducts[3]];
