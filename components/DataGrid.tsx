import React, { useState } from 'react';
import { DocumentFile, Column, ExtractionResult, ExtractionCell } from '../types';
import { FileText, Plus, Loader2, AlertCircle, CheckCircle2, ChevronRight, MoreHorizontal, Trash2 } from './Icons';

interface DataGridProps {
  documents: DocumentFile[];
  columns: Column[];
  results: ExtractionResult;
  onAddColumn: (triggerRect: DOMRect) => void;
  onEditColumn: (colId: string, triggerRect: DOMRect) => void;
  onColumnResize?: (colId: string, newWidth: number) => void;
  isTextWrapEnabled?: boolean;
  onCellClick: (docId: string, colId: string) => void;
  onDocClick: (docId: string) => void;
  onRemoveDoc: (docId: string) => void;
  selectedCell: { docId: string; colId: string } | null;
  onUpload?: (files: DocumentFile[]) => void;
  onDropFiles?: (files: File[]) => void;
}

export const DataGrid: React.FC<DataGridProps> = ({
  documents,
  columns,
  results,
  onAddColumn,
  onEditColumn,
  onColumnResize,
  isTextWrapEnabled,
  onCellClick,
  onDocClick,
  onRemoveDoc,
  selectedCell,
  onDropFiles
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [resizingColId, setResizingColId] = useState<string | null>(null);
  const [startX, setStartX] = useState(0);
  const [startWidth, setStartWidth] = useState(0);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      if (onDropFiles) {
        onDropFiles(files);
      }
    }
  };

  const handleResizeStart = (e: React.MouseEvent, colId: string, currentWidth: number) => {
    e.preventDefault();
    e.stopPropagation();
    setResizingColId(colId);
    setStartX(e.clientX);
    setStartWidth(currentWidth);
    
    const handleMouseMove = (moveEvent: MouseEvent) => {
        if (onColumnResize) {
            const diff = moveEvent.clientX - e.clientX;
            const newWidth = Math.max(100, startWidth + diff); // Min width 100px
            onColumnResize(colId, newWidth);
        }
    };

    const handleMouseUp = () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        setResizingColId(null);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };
  
  const getCellContent = (docId: string, colId: string) => {
    const cell = results[docId]?.[colId];
    
    if (columns.find(c => c.id === colId)?.status === 'extracting' && !cell) {
         return (
            <div className="flex items-center gap-2 opacity-50">
                <div className="w-4 h-1 bg-slate-200 rounded animate-pulse"></div>
                <div className="w-8 h-1 bg-slate-200 rounded animate-pulse"></div>
            </div>
         );
    }

    if (!cell) return <span className="text-slate-300 text-xs italic opacity-0 group-hover:opacity-100 transition-opacity">-</span>;
    
    const isSelected = selectedCell?.docId === docId && selectedCell?.colId === colId;

    return (
      <div className={`flex items-center justify-between w-full h-full ${isTextWrapEnabled ? 'items-start py-1' : ''}`}>
        <span 
            className={`text-sm ${isSelected ? 'font-medium' : ''} ${isTextWrapEnabled ? 'whitespace-pre-wrap break-words' : 'truncate max-w-[180px]'}`} 
            title={cell.value}
        >
            {cell.value}
        </span>
        <div className={`flex items-center gap-1 ${isTextWrapEnabled ? 'mt-1' : ''}`}>
            {cell.status === 'verified' && <CheckCircle2 className="w-3 h-3 text-emerald-500" />}
            {cell.confidence === 'Low' && cell.status !== 'verified' && <AlertCircle className="w-3 h-3 text-amber-500" />}
        </div>
      </div>
    );
  };

  return (
    <div 
        className={`flex-1 overflow-auto bg-white border-t border-slate-200 relative transition-all duration-200 ${isDragging ? 'bg-optura-gold/5' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
    >
      {isDragging && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-optura-gold/10 backdrop-blur-sm border-2 border-optura-gold border-dashed m-4 rounded-xl pointer-events-none">
            <div className="flex flex-col items-center animate-bounce">
                <Plus className="w-12 h-12 text-optura-gold mb-2" />
                <p className="text-lg font-bold text-optura-dark">Drop to add documents</p>
            </div>
        </div>
      )}

      <table className="w-full text-left border-collapse table-fixed">
        <thead className="bg-white sticky top-0 z-20 shadow-[0_1px_0_0_rgba(0,0,0,0.1)]">
          <tr>
            {/* Index Column Header - Sticky Left 0 */}
            <th className="w-12 border-b border-r border-slate-200 bg-white sticky left-0 z-30 shadow-[1px_0_0_0_rgba(0,0,0,0.05)]"></th>
            
            {/* Document Name Header - Sticky Left 12 (48px) */}
            <th className="p-3 border-b border-r border-slate-200 font-semibold text-xs text-slate-500 uppercase tracking-wider w-64 bg-white sticky left-12 z-30 shadow-[1px_0_0_0_rgba(0,0,0,0.05)]">
              Document
            </th>

            {columns.map((col) => (
              <th 
                key={col.id} 
                className="p-3 border-b border-r border-slate-200 font-semibold text-xs text-slate-500 uppercase tracking-wider group relative hover:bg-slate-50 transition-colors"
                style={{ width: col.width || 240 }}
              >
                <div className="flex items-center justify-between">
                    <div className="flex flex-col">
                        <span className="flex items-center gap-2 text-slate-700">
                            {col.name}
                            {col.status === 'extracting' && <Loader2 className="w-3 h-3 animate-spin text-optura-gold" />}
                        </span>
                    </div>
                    <button 
                        onClick={(e) => {
                            e.stopPropagation();
                            onEditColumn(col.id, e.currentTarget.getBoundingClientRect());
                        }}
                        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-slate-200 rounded text-slate-400 transition-opacity"
                    >
                        <MoreHorizontal className="w-3 h-3" />
                    </button>
                </div>
                {/* Resize Handle */}
                <div 
                    className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-optura-gold group-hover:bg-slate-300 transition-colors z-20"
                    onMouseDown={(e) => handleResizeStart(e, col.id, col.width || 240)}
                />
              </th>
            ))}
            <th className="p-2 border-b border-slate-200 w-16 bg-slate-50/30">
                <button 
                    onClick={(e) => onAddColumn(e.currentTarget.getBoundingClientRect())}
                    className="w-full h-full flex items-center justify-center text-slate-400 hover:text-optura-gold hover:bg-optura-gold/10 rounded transition-all"
                    title="Add Column"
                >
                    <Plus className="w-4 h-4" />
                </button>
            </th>
            {/* Fill remaining header space */}
             <th className="border-b border-slate-200 bg-slate-50/30"></th>
          </tr>
        </thead>
        <tbody className="text-sm text-slate-700 divide-y divide-slate-200">
          {documents.map((doc, index) => (
            <tr key={doc.id} className="group hover:bg-slate-50/80 transition-colors">
              {/* Index Column Body - Sticky Left 0 */}
              <td className="border-b border-r border-slate-200 bg-slate-50 text-[10px] text-slate-400 text-center font-mono sticky left-0 z-10 shadow-[1px_0_0_0_rgba(0,0,0,0.05)]">
                {index + 1}
              </td>
              
              {/* Document Name Body - Sticky Left 12 */}
              <td 
                className="p-3 border-b border-r border-slate-200 font-medium text-slate-900 bg-white group-hover:bg-slate-50 transition-colors sticky left-12 z-10 w-64 truncate shadow-[1px_0_0_0_rgba(0,0,0,0.05)] cursor-pointer hover:text-optura-gold relative"
                onClick={() => onDocClick(doc.id)}
                title="Click to preview document"
              >
                <div className="flex items-center gap-3 group/docname">
                    <div className="p-1.5 bg-slate-100 rounded text-slate-500">
                        <FileText className="w-3 h-3" />
                    </div>
                    <div className="flex-1 truncate pr-6">
                        <span title={doc.name}>{doc.name}</span>
                        <div className="text-[10px] text-slate-400 font-normal uppercase mt-0.5">{doc.size > 1024 ? `${(doc.size/1024).toFixed(0)} KB` : `${doc.size} B`}</div>
                    </div>

                    {/* Delete Button - Visible on Hover */}
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            if (window.confirm(`Are you sure you want to remove ${doc.name}?`)) {
                                onRemoveDoc(doc.id);
                            }
                        }}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 bg-white hover:bg-red-50 text-slate-400 hover:text-red-600 rounded-md shadow-sm opacity-0 group-hover:opacity-100 transition-all border border-slate-200 z-20"
                        title="Remove Document"
                    >
                        <Trash2 className="w-3.5 h-3.5" />
                    </button>
                </div>
              </td>
              {columns.map((col) => {
                const isSelected = selectedCell?.docId === doc.id && selectedCell?.colId === col.id;
                return (
                    <td 
                    key={`${doc.id}-${col.id}`} 
                    className={`p-3 border-b border-r border-slate-200 cursor-pointer transition-colors ${isTextWrapEnabled ? 'align-top' : 'h-14'}
                        ${isSelected ? 'bg-optura-gold/10 ring-inset ring-2 ring-optura-gold z-10' : 'hover:bg-slate-100/50'}
                    `}
                    onClick={() => onCellClick(doc.id, col.id)}
                    style={{ width: col.width || 240 }}
                    >
                    {getCellContent(doc.id, col.id)}
                    </td>
                );
              })}
              <td className="border-b border-slate-200"></td>
              <td className="border-b border-slate-200"></td>
            </tr>
          ))}
           {/* Empty State / Ghost Rows to keep grid structure */}
           {Array.from({ length: Math.max(5, 20 - documents.length) }).map((_, i) => (
            <tr key={`empty-${i}`}>
                <td className="border-b border-r border-slate-200 bg-slate-50/5 h-14 text-[10px] text-slate-300 text-center font-mono pt-4 sticky left-0 z-10">
                    {/* Number removed as requested for ghost rows */}
                </td>
                <td className="border-b border-r border-slate-200 bg-slate-50/5 sticky left-12 z-10"></td>
                {columns.map(c => <td key={c.id} className="border-b border-r border-slate-200 bg-slate-50/5" style={{ width: c.width || 240 }}></td>)}
                <td className="border-b border-slate-200"></td>
                <td className="border-b border-slate-200"></td>
            </tr>
           ))}
        </tbody>
      </table>
    </div>
  );
};