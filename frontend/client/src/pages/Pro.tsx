import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";
import { api, BillingStatus } from "@/lib/api";
import { toast } from "sonner";
import { Link } from "wouter";

function Check({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      <span className="text-green-600 font-bold shrink-0">✓</span>
      <span>{children}</span>
    </li>
  );
}

export default function Pro() {
  const { user, refreshUser } = useAuth();
  const { t } = useLocale();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(false);

  const params = new URLSearchParams(window.location.search);
  const checkoutResult = params.get("checkout"); // "success" | "canceled" | null

  useEffect(() => {
    api
      .getBillingStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoading(false));
    if (checkoutResult === "success") {
      // The webhook usually lands within seconds; refresh the plan so the
      // badge flips without a manual reload. If it hasn't arrived yet, the
      // next navigation re-checks /api/billing/status anyway.
      const timer = setTimeout(() => refreshUser().catch(() => {}), 4000);
      return () => clearTimeout(timer);
    }
  }, [checkoutResult]);

  const handleBuy = async () => {
    setBuying(true);
    try {
      const { url } = await api.createCheckout();
      window.location.href = url; // Stripe-hosted checkout (PCI scope stays with Stripe)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("pro.notConfigured"));
    } finally {
      setBuying(false);
    }
  };

  const userBadge = { name: user?.display_name || t("common.fallbackUser"), level: user?.level || "A1" };
  const isPro = status?.is_pro || user?.plan === "pro";
  const price = status?.pro_price_usd ?? 39;

  return (
    <DashboardLayout user={userBadge}>
      <div className="max-w-3xl mx-auto px-4 py-10">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold tracking-tight">{t("pro.title")}</h1>
          <p className="text-muted-foreground mt-2 text-lg">{t("pro.subtitle")}</p>
        </div>

        {checkoutResult === "success" && (
          <Card className="p-6 mb-6 border-green-500/50 bg-green-50 dark:bg-green-950/30">
            <h2 className="text-xl font-semibold text-green-700 dark:text-green-300">{t("pro.successTitle")}</h2>
            <p className="text-sm mt-1 text-green-700/80 dark:text-green-300/80">{t("pro.successBody")}</p>
            <Link href="/talk">
              <Button className="mt-4">🎤 {t("nav.talk")}</Button>
            </Link>
          </Card>
        )}

        {checkoutResult === "canceled" && (
          <Card className="p-6 mb-6 border-amber-500/50 bg-amber-50 dark:bg-amber-950/30">
            <h2 className="text-xl font-semibold">{t("pro.canceledTitle")}</h2>
            <p className="text-sm mt-1 text-muted-foreground">{t("pro.canceledBody")}</p>
          </Card>
        )}

        <div className="grid md:grid-cols-2 gap-4">
          {/* Free tier */}
          <Card className="p-6">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xl font-semibold">{t("pro.freeTitle")}</h2>
              {isPro === false && <Badge variant="secondary">{t("pro.compare.free")}</Badge>}
            </div>
            <p className="text-3xl font-bold mb-4">{t("pro.freePrice")}</p>
            <ul className="space-y-2">
              <Check>{t("pro.f1")}</Check>
              <Check>{t("pro.f2")}</Check>
              <Check>{t("pro.f3")}</Check>
            </ul>
          </Card>

          {/* Pro tier */}
          <Card className="p-6 border-primary ring-2 ring-primary/30 relative">
            <div className="absolute -top-3 left-1/2 -translate-x-1/2">
              <Badge className="bg-primary text-primary-foreground">{t("pro.badge")}</Badge>
            </div>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xl font-semibold">{t("pro.proTitle")}</h2>
              {isPro && <Badge>{t("pro.badge")}</Badge>}
            </div>
            <p className="text-3xl font-bold mb-1">${price}</p>
            <p className="text-xs text-muted-foreground mb-4">{t("pro.priceNote")}</p>
            <ul className="space-y-2 mb-6">
              <Check><strong>{t("pro.p1")}</strong></Check>
              <Check>{t("pro.p2")}</Check>
              <Check>{t("pro.p3")}</Check>
            </ul>
            {isPro ? (
              <Link href="/talk">
                <Button className="w-full" variant="secondary">🎤 {t("nav.talk")}</Button>
              </Link>
            ) : (
              <Button className="w-full" size="lg" onClick={handleBuy} disabled={buying || loading || !status?.stripe_configured}>
                {buying ? t("pro.ctaLoading") : t("pro.cta", { price: String(price) })}
              </Button>
            )}
            {!loading && !status?.stripe_configured && !isPro && (
              <p className="text-xs text-amber-600 mt-3">{t("pro.notConfigured")}</p>
            )}
            <p className="text-xs text-muted-foreground mt-3 text-center">🔒 {t("pro.secureNote")}</p>
          </Card>
        </div>

        {/* Comparison table */}
        <Card className="p-6 mt-6 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b">
                <th className="py-2 pr-4 font-medium text-muted-foreground"></th>
                <th className="py-2 pr-4">{t("pro.compare.free")}</th>
                <th className="py-2">{t("pro.compare.pro")}</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b">
                <td className="py-3 pr-4 text-muted-foreground">{t("pro.compare.row.talk")}</td>
                <td className="py-3 pr-4">{t("pro.compare.row.talkFree")}</td>
                <td className="py-3 font-semibold">{t("pro.compare.row.talkPro")}</td>
              </tr>
              <tr className="border-b">
                <td className="py-3 pr-4 text-muted-foreground">{t("pro.compare.row.lessons")}</td>
                <td className="py-3 pr-4">{t("pro.compare.row.unlimited")}</td>
                <td className="py-3 font-semibold">{t("pro.compare.row.unlimited")}</td>
              </tr>
              <tr>
                <td className="py-3 pr-4 text-muted-foreground">{t("pro.compare.row.payment")}</td>
                <td className="py-3 pr-4">{t("pro.compare.row.paymentFree")}</td>
                <td className="py-3 font-semibold">{t("pro.compare.row.paymentPro", { price: `$${price}` })}</td>
              </tr>
            </tbody>
          </table>
        </Card>
      </div>
    </DashboardLayout>
  );
}
