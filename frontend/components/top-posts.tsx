// frontend/components/top-posts.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { formatExact } from "@/lib/format";
import type { TopPost } from "@/lib/types";

interface TopPostsProps {
  insights: string;
  topPosts: TopPost[];
}

export function TopPosts({ insights, topPosts }: TopPostsProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Top Posts &amp; Engagement</CardTitle>
        {insights && (
          <p className="text-sm text-muted-foreground text-pretty">{insights}</p>
        )}
      </CardHeader>
      <CardContent>
        {topPosts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No top posts data.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tweet</TableHead>
                <TableHead className="text-right w-20">Likes</TableHead>
                <TableHead className="text-right w-20">RTs</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {topPosts.map((post, i) => (
                <TableRow key={i}>
                  <TableCell className="max-w-xs">
                    <p className="line-clamp-3 text-sm">{post.text}</p>
                  </TableCell>
                  <TableCell
                    className="text-right text-sm"
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {formatExact(post.likes)}
                  </TableCell>
                  <TableCell
                    className="text-right text-sm"
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {formatExact(post.retweets)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
