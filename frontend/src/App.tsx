import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MotionConfig } from 'motion/react';
import { useTheme } from '@/hooks/useTheme';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopNav } from '@/components/layout/TopNav';
import { Footer } from '@/components/layout/Footer';
import { CursorSpotlight } from '@/components/ui/CursorSpotlight';

// Pages
import { Home } from '@/pages/Home';
import { Dashboard } from '@/pages/Dashboard';
import { Verify } from '@/pages/Verify';
import { TextVerify } from '@/pages/TextVerify';
import { ArticleVerify } from '@/pages/ArticleVerify';
import { ImageAnalysis } from '@/pages/ImageAnalysis';
import { LiveNews } from '@/pages/LiveNews';
import { EvidenceExplorer } from '@/pages/EvidenceExplorer';
import { History } from '@/pages/History';
import { BlockchainRecords } from '@/pages/BlockchainRecords';
import { AuditExplorer } from '@/pages/AuditExplorer';
import { VerifyCertificate } from '@/pages/VerifyCertificate';
import { About } from '@/pages/About';

export function App() {
  const { isDark, toggleTheme } = useTheme();
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = useState(false);

  return (
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <div className="relative flex min-h-screen flex-col bg-background text-foreground transition-colors duration-200">
          {/* Global cursor-responsive ambient spotlight */}
          <CursorSpotlight />

          {/* Mobile slide-out navigation drawer (< lg viewports) */}
          <Sidebar
            isOpen={isMobileDrawerOpen}
            onClose={() => setIsMobileDrawerOpen(false)}
          />

          {/* Option A Sticky Top Navigation Bar */}
          <TopNav
            onToggleMobileDrawer={() => setIsMobileDrawerOpen((prev) => !prev)}
            isMobileDrawerOpen={isMobileDrawerOpen}
            isDark={isDark}
            onToggleTheme={toggleTheme}
          />

          {/* Main Content Area */}
          <main className="relative z-10 flex-1 overflow-x-clip">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/verify" element={<Verify />} />
              <Route path="/evidence" element={<EvidenceExplorer />} />
              <Route path="/live" element={<LiveNews />} />
              <Route path="/blockchain" element={<BlockchainRecords />} />
              <Route path="/about" element={<About />} />

              {/* Preserved legacy & direct-QR routes */}
              <Route path="/text" element={<TextVerify />} />
              <Route path="/article" element={<ArticleVerify />} />
              <Route path="/image" element={<ImageAnalysis />} />
              <Route path="/history" element={<History />} />
              <Route path="/audit" element={<AuditExplorer />} />
              <Route path="/verify-certificate" element={<VerifyCertificate />} />

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>

          <Footer />
        </div>
      </BrowserRouter>
    </MotionConfig>
  );
}

export default App;
