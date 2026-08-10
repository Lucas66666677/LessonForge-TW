import "./globals.css";

const appOrigin = (process.env.PUBLIC_APP_URL ?? "http://localhost:3000").replace(
  /\/$/,
  "",
);
const socialImage = `${appOrigin}/og.png`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant-TW">
      <head>
        <title>LessonForge TW｜補習班 AI 教材工作台</title>
        <meta
          name="description"
          content="讀取自有教材與班級脈絡，產生可編輯、核准與列印的完整英文教材包。"
        />
        <meta property="og:title" content="LessonForge TW" />
        <meta
          property="og:description"
          content="把班級脈絡與自有教材，鍛造成下一堂完整課程。"
        />
        <meta property="og:type" content="website" />
        <meta property="og:locale" content="zh_TW" />
        <meta property="og:image" content={socialImage} />
        <meta property="og:image:width" content="1536" />
        <meta property="og:image:height" content="1024" />
        <meta property="og:image:alt" content="LessonForge TW 教材工作台" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="LessonForge TW" />
        <meta name="twitter:image" content={socialImage} />
      </head>
      <body>{children}</body>
    </html>
  );
}
