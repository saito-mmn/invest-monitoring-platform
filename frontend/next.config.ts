import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // 公開MVPは画像最適化を使わない。未使用のImage Optimization APIを公開しない。
  images: { unoptimized: true },
};

export default nextConfig;
