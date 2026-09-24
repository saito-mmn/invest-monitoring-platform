/** NEXT_PUBLIC_* はbuild時に公開bundleへ埋め込まれる。秘密値は置かない。 */
export const PUBLIC_READ_ONLY = process.env.NEXT_PUBLIC_READ_ONLY === "true";
