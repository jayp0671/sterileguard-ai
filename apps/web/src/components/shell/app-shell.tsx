"use client";

import {
  Check,
  ChevronsLeft,
  ChevronsRight,
  Languages,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Search,
  Sun,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { type ReactNode, useEffect, useState } from "react";
import { BrandMark, Wordmark } from "@/components/brand";
import { DepartmentProvider, useDepartment } from "@/components/shell/department-context";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/hooks/use-me";
import { signOut } from "@/lib/auth/session";
import { env } from "@/lib/env";
import { type NavSection, navFor } from "@/lib/nav";
import { cn } from "@/lib/utils";

const COLLAPSE_KEY = "sg.sidebar.collapsed";
const showDevOnly = env.appEnv !== "production";

function SideNav({
  sections,
  collapsed,
  onNavigate,
}: {
  sections: NavSection[];
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex flex-col gap-5 px-2 py-4">
      {sections.map((section) => (
        <div key={section.label} className="flex flex-col gap-1">
          <p className={cn("engraved px-3 pb-1", collapsed && "sr-only")}>{section.label}</p>
          {section.items.map((item) => {
            const active =
              item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                title={collapsed ? item.label : undefined}
                className={cn(
                  "relative flex min-h-11 items-center gap-3 rounded-md px-3 text-sm text-sidebar-foreground transition-colors duration-150 hover:bg-sidebar-accent",
                  active &&
                    "bg-sidebar-accent font-medium text-sidebar-accent-foreground before:absolute before:inset-y-2 before:start-0 before:w-0.5 before:rounded-full before:bg-primary",
                  collapsed && "justify-center px-0",
                )}
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                <span className={cn(collapsed && "sr-only")}>{item.label}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function ThemeMenuItems() {
  const { theme, setTheme } = useTheme();
  return (
    <DropdownMenuRadioGroup value={theme ?? "system"} onValueChange={setTheme}>
      <DropdownMenuRadioItem value="light">
        <Sun aria-hidden /> Light
      </DropdownMenuRadioItem>
      <DropdownMenuRadioItem value="dark">
        <Moon aria-hidden /> Dark
      </DropdownMenuRadioItem>
      <DropdownMenuRadioItem value="system">
        <Monitor aria-hidden /> System
      </DropdownMenuRadioItem>
    </DropdownMenuRadioGroup>
  );
}

function TopBar({
  onOpenNav,
  onOpenPalette,
}: {
  onOpenNav: () => void;
  onOpenPalette: () => void;
}) {
  const { me, departmentId, departmentName, setDepartmentId } = useDepartment();
  const { resolvedTheme, setTheme } = useTheme();
  const memberships = me?.memberships ?? [];
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/95 px-3 lg:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="size-11 lg:hidden"
        onClick={onOpenNav}
        aria-label="Open navigation"
      >
        <Menu />
      </Button>
      {memberships.length > 1 ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="h-11 max-w-56 justify-start">
              <span className="truncate">{departmentName}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Department</DropdownMenuLabel>
            {memberships.map((m) => (
              <DropdownMenuItem
                key={m.department_id}
                onSelect={() => setDepartmentId(m.department_id)}
              >
                {m.department_id === departmentId ? (
                  <Check aria-hidden />
                ) : (
                  <span className="size-4" />
                )}
                {m.department_name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        <span className="truncate px-1 text-sm font-medium">{departmentName ?? ""}</span>
      )}
      <div className="ms-auto flex items-center gap-1">
        <Button
          variant="outline"
          className="h-11 gap-2 text-muted-foreground"
          onClick={onOpenPalette}
          aria-keyshortcuts="Control+K Meta+K"
        >
          <Search aria-hidden />
          <span className="hidden sm:inline">Go to…</span>
          <kbd className="tabular hidden rounded-sm border px-1.5 text-xs sm:inline">Ctrl K</kbd>
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="size-11" aria-label="Language">
              <Languages />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Language</DropdownMenuLabel>
            <DropdownMenuRadioGroup value="en">
              <DropdownMenuRadioItem value="en">English</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <p className="px-2 py-1.5 text-xs text-muted-foreground">More languages in SG-27.</p>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button
          variant="ghost"
          size="icon"
          className="size-11"
          aria-label={resolvedTheme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          {resolvedTheme === "dark" ? <Sun /> : <Moon />}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="size-11" aria-label="Account">
              <UserRound />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="truncate">
              {me?.display_name ?? "Signed in"}
            </DropdownMenuLabel>
            <DropdownMenuItem asChild>
              <Link href="/app/settings">Settings</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Theme</DropdownMenuLabel>
            <ThemeMenuItems />
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void signOut("user")}>
              <LogOut aria-hidden /> Sign out
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void signOut("user", "global")}>
              <LogOut aria-hidden /> Sign out of all devices
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

function CommandPalette({
  open,
  onOpenChange,
  sections,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sections: NavSection[];
}) {
  const router = useRouter();
  const { setTheme } = useTheme();
  const run = (fn: () => void) => {
    onOpenChange(false);
    fn();
  };
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Command palette">
      <CommandInput placeholder="Go to a page or run a command" />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>
        <CommandGroup heading="Pages">
          {sections.flatMap((s) =>
            s.items.map((item) => (
              <CommandItem key={item.href} onSelect={() => run(() => router.push(item.href))}>
                <item.icon aria-hidden /> {item.label}
              </CommandItem>
            )),
          )}
          <CommandItem onSelect={() => run(() => router.push("/app/history"))}>
            Open recent shifts
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Theme">
          <CommandItem onSelect={() => run(() => setTheme("light"))}>
            <Sun aria-hidden /> Light theme
          </CommandItem>
          <CommandItem onSelect={() => run(() => setTheme("dark"))}>
            <Moon aria-hidden /> Dark theme
          </CommandItem>
          <CommandItem onSelect={() => run(() => setTheme("system"))}>
            <Monitor aria-hidden /> System theme
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Account">
          <CommandItem onSelect={() => run(() => void signOut("user"))}>
            <LogOut aria-hidden /> Sign out
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}

function ShellFrame({ children, failed }: { children: ReactNode; failed: boolean }) {
  const { roles, me } = useDepartment();
  const sections = navFor(roles, { showDevOnly });
  const [collapsed, setCollapsed] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      // ignore
    }
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggle = () => {
    setCollapsed((v) => {
      try {
        window.localStorage.setItem(COLLAPSE_KEY, v ? "0" : "1");
      } catch {
        // ignore
      }
      return !v;
    });
  };

  return (
    <div className="flex min-h-full flex-1">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:start-4 focus:top-4"
      >
        Skip to content
      </a>
      <aside
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col border-e bg-sidebar transition-[width] duration-200 lg:flex",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <div
          className={cn("flex h-14 items-center border-b px-4", collapsed && "justify-center px-0")}
        >
          {collapsed ? (
            <BrandMark className="text-primary" title="SterileGuard" />
          ) : (
            <Link href="/app" aria-label="SterileGuard home">
              <Wordmark />
            </Link>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          {me ? (
            <SideNav sections={sections} collapsed={collapsed} />
          ) : (
            <div className="flex flex-col gap-2 p-4" aria-busy="true">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-9" />
              ))}
            </div>
          )}
        </div>
        <Button
          variant="ghost"
          className="m-2 h-11"
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
        >
          {collapsed ? <ChevronsRight /> : <ChevronsLeft />}
        </Button>
      </aside>
      <Sheet open={navOpen} onOpenChange={setNavOpen}>
        <SheetContent side="left" className="w-72 bg-sidebar p-0">
          <SheetTitle className="flex h-14 items-center border-b px-4">
            <Wordmark />
          </SheetTitle>
          <SideNav sections={sections} collapsed={false} onNavigate={() => setNavOpen(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenNav={() => setNavOpen(true)} onOpenPalette={() => setPaletteOpen(true)} />
        <main id="main" tabIndex={-1} className="flex-1 px-4 py-6 outline-none lg:px-8">
          {failed ? (
            <ErrorState
              title="Could not load your account"
              detail="The API did not answer. Check your connection and try again."
              onRetry={() => window.location.reload()}
            />
          ) : (
            children
          )}
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} sections={sections} />
    </div>
  );
}

/** Authenticated shell: role-filtered sidebar, top bar, command palette (Ctrl/Cmd+K). */
export function AppShell({ children }: { children: ReactNode }) {
  const me = useMe();
  return (
    <DepartmentProvider me={me.data}>
      <ShellFrame failed={me.isError}>{children}</ShellFrame>
    </DepartmentProvider>
  );
}
