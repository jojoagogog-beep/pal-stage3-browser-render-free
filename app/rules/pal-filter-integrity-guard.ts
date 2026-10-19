import {makeMeta} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Filter Integrity Guard","filter-integrity","Review missing, inconsistent, and fragmented filter values in options, tags, and selected product metafields.");
// The Filter Integrity Guard is implemented in the dedicated feature route
// (app/special/filter-integrity/ui.tsx). No generic catalog audit fallback.
export function auditCatalog(): never {throw new Error("Filter Integrity Guard requires specialized audit route");}
