// frontend/components/profile-card.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCount, formatExact } from "@/lib/format";
import type { UserInfo } from "@/lib/types";

interface ProfileCardProps {
  userInfo: UserInfo;
  tweetsParsed: number;
}

export function ProfileCard({ userInfo, tweetsParsed }: ProfileCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-balance">
          {userInfo.display_name || userInfo.username}
        </CardTitle>
        <p className="text-sm text-muted-foreground">@{userInfo.username}</p>
      </CardHeader>
      <CardContent className="space-y-2">
        {userInfo.bio && (
          <p className="text-sm leading-relaxed">{userInfo.bio}</p>
        )}
        <dl
          className="grid grid-cols-3 gap-2 pt-2 text-sm"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          <div>
            <dt className="text-muted-foreground">Followers</dt>
            <dd className="font-medium">{formatCount(userInfo.followers)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Following</dt>
            <dd className="font-medium">{formatCount(userInfo.following)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Tweets</dt>
            <dd className="font-medium">{formatCount(userInfo.tweets_count)}</dd>
          </div>
        </dl>
        <p className="text-xs text-muted-foreground pt-1">
          {formatExact(tweetsParsed)} tweets analyzed
        </p>
      </CardContent>
    </Card>
  );
}
