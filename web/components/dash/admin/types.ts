export type Person = { name?: string; handle?: string; avatar?: string };
export type Table = { name: string; bytes: number | null; rows?: number };
export type AdminData = {
  accounts: { region: string; count: number; expired: number }[];
  expired: ({ userId: string; region: string; since: string } & Person)[];
  failingReads: ({ userId: string; lastRead: string; error: string } & Person)[];
  sources: { source: string; checkedAt: string; bytes: number; etag: boolean }[];
  simai?: { read: number; refused: number; waiting: number; sheets?: number; sheetBytes?: number; checked_at?: string };
  updates?: Record<string, { running?: boolean; ok?: boolean; said?: string; at?: string; seconds?: number }>;
  busiest: ({ userId: string; plays: number } & Person)[];
  activity: { day: string; plays: number; people: number }[];
  growth: { day: string; accounts: number }[];
  store: {
    bytes: number; freeBytes: number; walBytes: number; tables: Table[];
    plays: number; judgements: number; ratingPoints: number; playCounts: number; oldestPlay: string | null;
  };
  live: Record<string, number | boolean | number[] | undefined>;
  generatedAt: string;
  accounts_list?: Account[];
  guilds_list?: Guild[];
};

export type Guild = {
  id: string; name: string; icon: string; members: number;
  ownerId: string; owner: string; joinedAt: string; shard: number; configured: boolean;
};

export type Account = Person & {
  userId: string; region: string; player: string; rating: number;
  linkedAt: string; readAt: string; seenAt: string;
  expired: boolean; shared: boolean; plays: number; judged: number;
};

export type Detail = Person & {
  userId: string; region: string; player: string; title: string; dan: string; rating: number;
  totalPlayCount: number; charts: number; linkedAt: string; readAt: string; seenAt: string;
  expired: string; shared: boolean;
  settings: Record<string, string | boolean>;
  counts: Record<string, number | string | null>;
  quietRead: { readAt: string; added: number; error: string };
  history: { recordedAt: string; rating: number }[];
  activity: { day: string; plays: number }[];
};
