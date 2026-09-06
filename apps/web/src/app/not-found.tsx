import Link from "next/link";

export default function NotFound() {
  return <main className="center-state"><h1>页面不存在</h1><p>这个地址可能已经失效。</p><Link href="/projects" className="button button-primary">返回项目</Link></main>;
}
