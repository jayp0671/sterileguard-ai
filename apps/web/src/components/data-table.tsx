"use client";

import {
  type ColumnDef,
  columnFilteringFeature,
  columnVisibilityFeature,
  createColumnHelper,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  filterFn_includesString,
  globalFilteringFeature,
  type RowData,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  sortFn_datetime,
  sortFn_text,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, Columns3, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** Feature set every DataTable uses: sort, filter, paginate, toggle columns. */
export const dataTableFeatures = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  rowSortingFeature,
  rowPaginationFeature,
  columnVisibilityFeature,
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  filterFns: { includesString: filterFn_includesString },
  sortFns: {
    alphanumeric: sortFn_alphanumeric,
    basic: sortFn_basic,
    datetime: sortFn_datetime,
    text: sortFn_text,
  },
  columnMeta: {} as { numeric?: boolean },
});

export type DataTableFeatures = typeof dataTableFeatures;
export type DataTableColumn<T extends RowData> = ColumnDef<DataTableFeatures, T>;
export const dataTableColumns = <T extends RowData>() => createColumnHelper<DataTableFeatures, T>();

/** Rows as CSV text for the export hook. Values are quoted when needed. */
export function toCsv(headers: string[], rows: unknown[][]): string {
  const cell = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  return [headers, ...rows].map((r) => r.map(cell).join(",")).join("\n");
}

export function DataTable<T extends RowData>({
  data,
  columns,
  caption,
  pageSize = 20,
  filterPlaceholder = "Filter rows",
  onExportCsv,
  className,
}: {
  data: T[];
  columns: DataTableColumn<T>[];
  caption: string;
  pageSize?: number;
  filterPlaceholder?: string;
  /** Receives the filtered and sorted rows as CSV; the page decides how to download it. */
  onExportCsv?: (csv: string) => void;
  className?: string;
}) {
  const table = useTable({
    features: dataTableFeatures,
    columns,
    data,
    initialState: { pagination: { pageIndex: 0, pageSize } },
    globalFilterFn: "includesString",
  });
  const leaf = table.getAllLeafColumns();
  const exportCsv = () => {
    const visible = table.getVisibleLeafColumns();
    const rows = table.getSortedRowModel().rows.map((r) => visible.map((c) => r.getValue(c.id)));
    onExportCsv?.(
      toCsv(
        visible.map((c) => (typeof c.columnDef.header === "string" ? c.columnDef.header : c.id)),
        rows,
      ),
    );
  };
  const { pageIndex } = table.state.pagination;
  const total = table.getFilteredRowModel().rows.length;

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label={filterPlaceholder}
          placeholder={filterPlaceholder}
          value={String(table.state.globalFilter ?? "")}
          onChange={(e) => table.setGlobalFilter(e.target.value)}
          className="h-11 max-w-xs"
        />
        <div className="ms-auto flex gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="h-11">
                <Columns3 aria-hidden /> Columns
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Show columns</DropdownMenuLabel>
              {leaf.map((col) => (
                <DropdownMenuCheckboxItem
                  key={col.id}
                  checked={col.getIsVisible()}
                  onCheckedChange={(v) => col.toggleVisibility(Boolean(v))}
                >
                  {typeof col.columnDef.header === "string" ? col.columnDef.header : col.id}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          {onExportCsv ? (
            <Button variant="outline" className="h-11" onClick={exportCsv}>
              <Download aria-hidden /> CSV
            </Button>
          ) : null}
        </div>
      </div>
      <div className="overflow-x-auto rounded-md border bg-card">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id} className="border-b">
                {group.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  const numeric = header.column.columnDef.meta?.numeric;
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={
                        sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"
                      }
                      className={cn(
                        "engraved h-10 px-3 font-medium",
                        numeric ? "text-end" : "text-start",
                      )}
                    >
                      {header.isPlaceholder ? null : header.column.getCanSort() ? (
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          className="inline-flex min-h-11 items-center gap-1 uppercase"
                        >
                          <table.FlexRender header={header} />
                          {sorted === "asc" ? (
                            <ArrowUp className="size-3.5" aria-hidden />
                          ) : sorted === "desc" ? (
                            <ArrowDown className="size-3.5" aria-hidden />
                          ) : (
                            <ArrowUpDown className="size-3.5 opacity-50" aria-hidden />
                          )}
                        </button>
                      ) : (
                        <table.FlexRender header={header} />
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b last:border-0 hover:bg-muted/50">
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={cn(
                      "h-11 px-3",
                      cell.column.columnDef.meta?.numeric && "tabular text-end",
                    )}
                  >
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
            {total === 0 ? (
              <tr>
                <td colSpan={leaf.length} className="h-20 text-center text-muted-foreground">
                  No matching rows
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
        <span className="tabular">
          {total} rows · page {total ? pageIndex + 1 : 0} of {table.getPageCount()}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            className="h-11"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            className="h-11"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
