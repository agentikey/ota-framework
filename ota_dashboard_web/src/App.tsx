import { Link, Route, Routes, useLocation } from "react-router-dom";
import { ApprovalQueuePage } from "./routes/ApprovalQueue";
import { AuditLogPage } from "./routes/AuditLog";
import { WhyPage } from "./routes/Why";
import { KnobsPage } from "./routes/Knobs";
import { FleetPage } from "./routes/Fleet";
import { CriticalBanner } from "./components/CriticalBanner";

const NAV = [
  { path: "/", label: "Approvals" },
  { path: "/audit", label: "Audit" },
  { path: "/why", label: "/why" },
  { path: "/knobs", label: "Knobs" },
  { path: "/fleet", label: "Fleet" },
];

export default function App() {
  const location = useLocation();
  return (
    <div className="min-h-screen flex flex-col">
      <CriticalBanner />
      <header className="border-b bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center gap-6">
          <h1 className="text-lg font-semibold tracking-tight">OTA Dashboard</h1>
          <nav className="flex gap-1">
            {NAV.map((item) => {
              const active =
                item.path === "/"
                  ? location.pathname === "/"
                  : location.pathname.startsWith(item.path);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={
                    "px-3 py-1.5 rounded-md text-sm transition-colors " +
                    (active
                      ? "bg-zinc-900 text-white"
                      : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100")
                  }
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
        <Routes>
          <Route path="/" element={<ApprovalQueuePage />} />
          <Route path="/audit" element={<AuditLogPage />} />
          <Route path="/why" element={<WhyPage />} />
          <Route path="/why/:emailId" element={<WhyPage />} />
          <Route path="/knobs" element={<KnobsPage />} />
          <Route path="/fleet" element={<FleetPage />} />
        </Routes>
      </main>
    </div>
  );
}
