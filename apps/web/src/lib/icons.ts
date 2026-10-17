import type { ComponentType, CSSProperties } from "react";

// Named re-exports from lucide-react. Named imports let Rollup tree-shake the
// icon library (the old `import *` pulled all ~1,450 icons into the bundle).
// To add an icon: import it below and export it with the `Icon` prefix.
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Archive,
  ArrowDownUp,
  ArrowLeft,
  ArrowLeftRight,
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  Ban,
  BarChart3,
  Bell,
  Braces,
  Building2,
  CalendarDays,
  Check,
  CheckCheck,
  CheckCircle2,
  CheckSquare,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Clock,
  CloudUpload,
  Columns3,
  Command,
  Copy,
  Cpu,
  Database,
  Download,
  Edit,
  ExternalLink,
  Eye,
  FileSpreadsheet,
  FileText,
  FileWarning,
  Filter,
  Flame,
  FoldVertical,
  Gauge,
  Globe,
  HardDrive,
  Hash,
  History,
  Image,
  Inbox,
  Info,
  KeyRound,
  LayoutDashboard,
  Layers,
  Link,
  ListChecks,
  Loader2,
  Lock,
  LogIn,
  LogOut,
  Mail,
  MailOpen,
  MailPlus,
  MapPin,
  Merge,
  MonitorSmartphone,
  MoreHorizontal,
  MoreVertical,
  Pause,
  Pencil,
  Phone,
  Play,
  Plus,
  RefreshCcw,
  Rows3,
  Save,
  Search,
  SearchX,
  Send,
  Server,
  Settings,
  Shield,
  ShieldCheck,
  Sidebar as SidebarIconSource,
  SidebarClose,
  SidebarOpen,
  SlidersHorizontal,
  Sparkle,
  Sparkles,
  Split,
  Square,
  SquareCheck,
  Star,
  Table2,
  Tag,
  Target,
  Terminal,
  TrendingDown,
  TrendingUp,
  TriangleAlert,
  Trash2,
  Undo2,
  UnfoldVertical,
  Upload,
  User,
  UserCheck,
  UserPlus,
  Users,
  WandSparkles,
  X,
} from "lucide-react";

type IconComponent = ComponentType<{
  className?: string;
  size?: number | string;
  strokeWidth?: number;
  color?: string;
  style?: CSSProperties;
}>;

export const IconLayoutDashboard: IconComponent = LayoutDashboard;
export const IconBuilding2: IconComponent = Building2;
export const IconUsers: IconComponent = Users;
export const IconTable2: IconComponent = Table2;
export const IconHash: IconComponent = Hash;
export const IconSearch: IconComponent = Search;
export const IconFileSpreadsheet: IconComponent = FileSpreadsheet;
export const IconAlertTriangle: IconComponent = AlertTriangle;
export const IconSparkles: IconComponent = Sparkles;
export const IconActivity: IconComponent = Activity;
export const IconSettings: IconComponent = Settings;
export const IconSidebar: IconComponent = SidebarIconSource;
export const IconSidebarCollapse: IconComponent = SidebarClose;
export const IconSidebarExpand: IconComponent = SidebarOpen;
export const IconCommand: IconComponent = Command;
export const IconPlus: IconComponent = Plus;
export const IconSearchX: IconComponent = SearchX;
export const IconUser: IconComponent = User;
export const IconLogout: IconComponent = LogOut;
export const IconLogIn: IconComponent = LogIn;
export const IconLogOut: IconComponent = LogOut;
export const IconMail: IconComponent = Mail;
export const IconSend: IconComponent = Send;
export const IconBell: IconComponent = Bell;
export const IconMailOpen: IconComponent = MailOpen;
export const IconPhone: IconComponent = Phone;
export const IconLink: IconComponent = Link;
export const IconMapPin: IconComponent = MapPin;
export const IconListChecks: IconComponent = ListChecks;
export const IconCheck: IconComponent = Check;
export const IconX: IconComponent = X;
export const IconAlertCircle: IconComponent = AlertCircle;
export const IconInfo: IconComponent = Info;
export const IconClipboardList: IconComponent = ClipboardList;
export const IconCopy: IconComponent = Copy;
export const IconCheckCheck: IconComponent = CheckCheck;
export const IconLoader2: IconComponent = Loader2;
export const IconCheckCircle2: IconComponent = CheckCircle2;
export const IconSquare: IconComponent = Square;
export const IconSquareCheck: IconComponent = SquareCheck;
export const IconChevronDown: IconComponent = ChevronDown;
export const IconChevronRight: IconComponent = ChevronRight;
export const IconChevronLeft: IconComponent = ChevronLeft;
export const IconRefreshCcw: IconComponent = RefreshCcw;
export const IconDownload: IconComponent = Download;
export const IconUpload: IconComponent = Upload;
export const IconMoreHorizontal: IconComponent = MoreHorizontal;
export const IconMoreVertical: IconComponent = MoreVertical;
export const IconEdit: IconComponent = Edit;
export const IconTrash2: IconComponent = Trash2;
export const IconArchive: IconComponent = Archive;
export const IconRotary: IconComponent = RefreshCcw;
export const IconArrowLeft: IconComponent = ArrowLeft;
export const IconSparkle: IconComponent = Sparkle;
export const IconTarget: IconComponent = Target;
export const IconGauge: IconComponent = Gauge;
export const IconUserCheck: IconComponent = UserCheck;
export const IconArrowRightLeft: IconComponent = ArrowLeftRight;
export const IconFlame: IconComponent = Flame;
export const IconArrowUpRight: IconComponent = ArrowUpRight;
export const IconArrowRight: IconComponent = ArrowRight;
export const IconExternalLink: IconComponent = ExternalLink;
export const IconBarChart3: IconComponent = BarChart3;
export const IconTrendingUp: IconComponent = TrendingUp;
export const IconTrendingDown: IconComponent = TrendingDown;
export const IconCalendarDays: IconComponent = CalendarDays;
export const IconClock: IconComponent = Clock;
export const IconBadgeCheck: IconComponent = BadgeCheck;
export const IconImage: IconComponent = Image;
export const IconCheckSquare: IconComponent = CheckSquare;
export const IconFoldVertical: IconComponent = FoldVertical;
export const IconUnfoldVertical: IconComponent = UnfoldVertical;
export const IconShield: IconComponent = Shield;
export const IconTag: IconComponent = Tag;
export const IconDatabase: IconComponent = Database;
export const IconFileText: IconComponent = FileText;
export const IconHistory: IconComponent = History;
export const IconStar: IconComponent = Star;
export const IconMerge: IconComponent = Merge;
export const IconInbox: IconComponent = Inbox;
export const IconGlobe: IconComponent = Globe;
export const IconCpu: IconComponent = Cpu;
export const IconCalendar: IconComponent = CalendarDays;
export const IconFilter: IconComponent = Filter;
export const IconLock: IconComponent = Lock;
export const IconUserPlus: IconComponent = UserPlus;
export const IconChevronRightIcon: IconComponent = ChevronRight;
export const IconChevronLeftIcon: IconComponent = ChevronLeft;
export const IconChevronDownIcon: IconComponent = ChevronDown;
export const IconRefreshIcon: IconComponent = RefreshCcw;
export const IconDownloadIcon: IconComponent = Download;
export const IconUploadIcon: IconComponent = Upload;
export const IconMoreHorizontalIcon: IconComponent = MoreHorizontal;
export const IconMoreVerticalIcon: IconComponent = MoreVertical;
export const IconEditIcon: IconComponent = Edit;
export const IconTrashIcon: IconComponent = Trash2;
export const IconArchiveIcon: IconComponent = Archive;
export const IconLinkIcon: IconComponent = Link;
export const IconMailIcon: IconComponent = Mail;
export const IconPhoneIcon: IconComponent = Phone;
export const IconUserIcon: IconComponent = User;
export const IconBuildingIcon: IconComponent = Building2;
export const IconMapPinIcon: IconComponent = MapPin;
export const IconHashIcon: IconComponent = Hash;
export const IconListChecksIcon: IconComponent = ListChecks;
export const IconCheckIcon: IconComponent = Check;
export const IconXIcon: IconComponent = X;
export const IconAlertCircleIcon: IconComponent = AlertCircle;
export const IconInfoIcon: IconComponent = Info;
export const IconClipboardListIcon: IconComponent = ClipboardList;
export const IconCopyIcon: IconComponent = Copy;
export const IconCheckCheckIcon: IconComponent = CheckCheck;
export const IconLoaderIcon: IconComponent = Loader2;
export const IconCheckCircleIcon: IconComponent = CheckCircle2;
export const IconSquareIcon: IconComponent = Square;
export const IconSquareCheckIconAlt: IconComponent = SquareCheck;
export const IconRefreshCcwIcon: IconComponent = RefreshCcw;
export const IconDownloadIconAlt: IconComponent = Download;
export const IconUploadIconAlt: IconComponent = Upload;
export const IconMoreHorizontalIconAlt: IconComponent = MoreHorizontal;
export const IconMoreVerticalIconAlt: IconComponent = MoreVertical;
export const IconEditIconAlt: IconComponent = Edit;
export const IconTrashIconAlt: IconComponent = Trash2;
export const IconArchiveIconAlt: IconComponent = Archive;
export const IconExternalLinkIcon: IconComponent = ExternalLink;
export const IconBarChartIcon: IconComponent = BarChart3;
export const IconTrendingUpIcon: IconComponent = TrendingUp;
export const IconTrendingDownIcon: IconComponent = TrendingDown;
export const IconCalendarIcon: IconComponent = CalendarDays;
export const IconClockIcon: IconComponent = Clock;
export const IconBadgeCheckIcon: IconComponent = BadgeCheck;
export const IconImageIcon: IconComponent = Image;
export const IconCheckSquareIcon: IconComponent = CheckSquare;
export const IconFoldIcon: IconComponent = FoldVertical;
export const IconUnfoldIcon: IconComponent = UnfoldVertical;
export const IconHashTwoIcon: IconComponent = Hash;
export const IconShieldIcon: IconComponent = Shield;
export const IconTagsIcon: IconComponent = Tag;
export const IconDatabaseIconAlt: IconComponent = Database;
export const IconFileTextIcon: IconComponent = FileText;
export const IconHistoryIcon: IconComponent = History;
export const IconStarIcon: IconComponent = Star;
export const IconMergeIcon: IconComponent = Merge;
export const IconInboxIcon: IconComponent = Inbox;
export const IconBracesIcon: IconComponent = Braces;
export const IconTable2Icon: IconComponent = Table2;
export const IconColumns3: IconComponent = Columns3;
export const IconRows3: IconComponent = Rows3;
export const IconSlidersHorizontalIcon: IconComponent = SlidersHorizontal;
export const IconCloudUpload: IconComponent = CloudUpload;
export const IconFileWarning: IconComponent = FileWarning;
export const IconWandSparkles: IconComponent = WandSparkles;
export const IconEyeIcon: IconComponent = Eye;
export const IconKeyRound: IconComponent = KeyRound;
export const IconMonitorSmartphone: IconComponent = MonitorSmartphone;
export const IconShieldCheck: IconComponent = ShieldCheck;
export const IconServer: IconComponent = Server;
export const IconArrowLeftRight: IconComponent = ArrowLeftRight;
export const IconSplit: IconComponent = Split;
export const IconSave: IconComponent = Save;
export const IconHardDrive: IconComponent = HardDrive;
export const IconTerminal: IconComponent = Terminal;
export const IconTriangleAlert: IconComponent = TriangleAlert;
export const IconPlay: IconComponent = Play;
export const IconPause: IconComponent = Pause;
export const IconMailPlus: IconComponent = MailPlus;
export const IconUndo2: IconComponent = Undo2;
export const IconLayers: IconComponent = Layers;
export const IconPencil: IconComponent = Pencil;
export const IconBan: IconComponent = Ban;
export const IconArrowDownUp: IconComponent = ArrowDownUp;
