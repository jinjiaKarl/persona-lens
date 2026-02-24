// frontend/components/writing-style.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface WritingStyleProps {
  text: string;
}

export function WritingStyle({ text }: WritingStyleProps) {
  return (
    <Card>
      <CardHeader><CardTitle>Writing Style</CardTitle></CardHeader>
      <CardContent>
        {text ? (
          <p className="text-sm leading-relaxed">{text}</p>
        ) : (
          <p className="text-sm text-muted-foreground">No writing style data.</p>
        )}
      </CardContent>
    </Card>
  );
}
