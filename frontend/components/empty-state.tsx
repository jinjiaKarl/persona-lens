// frontend/components/empty-state.tsx
export function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <h2 className="text-2xl font-semibold text-balance">
        Analyze any X/Twitter KOL
      </h2>
      <p className="mt-3 max-w-md text-muted-foreground text-pretty">
        Enter a username above to extract their product mentions, writing style,
        and engagement patterns.
      </p>
    </div>
  );
}
