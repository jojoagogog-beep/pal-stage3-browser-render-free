import { randomUUID } from "node:crypto";
import db from "../../db.server";

export async function getSelectedMetafields(shop: string) {
  const rows = await db.$queryRaw<Array<{ selectedMetafields: string }>>`
    SELECT "selectedMetafields"
    FROM "FilterConfig"
    WHERE "shop" = ${shop}
    LIMIT 1
  `;
  return rows[0]?.selectedMetafields || "";
}

export async function saveSelectedMetafields(shop: string, selectedMetafields: string) {
  const now = new Date();
  await db.$executeRaw`
    INSERT INTO "FilterConfig" ("id", "shop", "selectedMetafields", "createdAt", "updatedAt")
    VALUES (${randomUUID()}, ${shop}, ${selectedMetafields}, ${now}, ${now})
    ON CONFLICT("shop") DO UPDATE SET
      "selectedMetafields" = excluded."selectedMetafields",
      "updatedAt" = excluded."updatedAt"
  `;
}

export async function deleteFilterConfig(shop: string) {
  await db.$executeRaw`DELETE FROM "FilterConfig" WHERE "shop" = ${shop}`;
}
