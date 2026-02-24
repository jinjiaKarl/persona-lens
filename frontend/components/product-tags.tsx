// frontend/components/product-tags.tsx
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProductItem } from "@/lib/types";

interface ProductTagsProps {
  products: ProductItem[];
}

export function ProductTags({ products }: ProductTagsProps) {
  if (products.length === 0) {
    return (
      <Card>
        <CardHeader><CardTitle>Products Mentioned</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No products detected.</p>
        </CardContent>
      </Card>
    );
  }

  // Group by category
  const grouped: Record<string, string[]> = {};
  for (const { product, category } of products) {
    (grouped[category] ??= []).push(product);
  }

  return (
    <Card>
      <CardHeader><CardTitle>Products Mentioned</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {Object.entries(grouped).map(([cat, items]) => (
          <div key={cat}>
            <p className="text-xs font-medium text-muted-foreground mb-1">
              {cat} ({items.length})
            </p>
            <div className="flex flex-wrap gap-1">
              {items.map((p) => (
                <Badge key={p} variant="secondary">{p}</Badge>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
