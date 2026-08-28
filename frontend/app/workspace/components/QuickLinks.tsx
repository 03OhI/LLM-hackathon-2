"use client";

// GitHub/Figma/Notion 바로가기 — 기존 workspace.resources를 재사용한다(별도 API 없음).
// 링크가 없으면 "OO 연결하기" 버튼을 보여주고, 클릭하면 기존 ResourceLink 등록 폼으로
// provider를 미리 선택한 채 스크롤/포커스한다.

import type { ResourceLink, ResourceProvider } from "@/lib/workspace-api";

const QUICK_LINK_PROVIDERS: { provider: ResourceProvider; label: string }[] = [
  { provider: "GITHUB", label: "GitHub" },
  { provider: "FIGMA", label: "Figma" },
  { provider: "NOTION", label: "Notion" },
];

export function QuickLinks({
  resources,
  onConnect,
}: {
  resources: ResourceLink[];
  onConnect: (provider: ResourceProvider) => void;
}) {
  return (
    <section className="workspace-quicklinks workspace-span-2" aria-label="GitHub/Figma/Notion 바로가기">
      {QUICK_LINK_PROVIDERS.map(({ provider, label }) => {
        const resource = resources.find((r) => r.provider === provider);
        return (
          <div key={provider} className="workspace-quicklink-card">
            <span className="workspace-quicklink-service">{label}</span>
            {resource ? (
              <>
                <span className="workspace-quicklink-title">{resource.title}</span>
                <a
                  href={resource.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="button-muted workspace-quicklink-open"
                >
                  열기
                </a>
              </>
            ) : (
              <button type="button" className="button-muted" onClick={() => onConnect(provider)}>
                {label} 연결하기
              </button>
            )}
          </div>
        );
      })}
    </section>
  );
}
