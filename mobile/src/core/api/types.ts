export interface ResponseLike {
  readonly ok: boolean;
  readonly status: number;
  readonly headers: Readonly<{ get(name: string): string | null }>;
  json(): Promise<unknown>;
}

export type FetchLike = (
  input: string,
  init: Readonly<{
    method: string;
    headers: Readonly<Record<string, string>>;
    body?: string;
  }>,
) => Promise<ResponseLike>;

export type Clock = () => Date;
