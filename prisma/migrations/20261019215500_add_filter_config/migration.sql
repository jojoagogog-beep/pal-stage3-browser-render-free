
CREATE TABLE IF NOT EXISTS "FilterConfig" (
    "id" TEXT NOT NULL,
    "shop" TEXT NOT NULL,
    "selectedMetafields" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "FilterConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "FilterConfig_shop_key" ON "FilterConfig"("shop");
