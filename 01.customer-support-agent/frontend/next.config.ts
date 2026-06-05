import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 홈 디렉터리의 다른 lockfile 때문에 워크스페이스 루트가 잘못 추론되는 것을 막는다.
  // 이 frontend 폴더를 Turbopack 루트로 고정.
  turbopack: {
    root: import.meta.dirname,
  },
};

export default nextConfig;
