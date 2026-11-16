'use client';

import React from 'react';
import Image from 'next/image';
import Link from 'next/link';

type BrandLogoProps = {
  href?: string | null;
  /** mark = square W+ icon; full = logo with wordmark */
  variant?: 'mark' | 'full';
  size?: 'sm' | 'md' | 'lg';
  showTagline?: boolean;
  className?: string;
};

const MARK = {
  sm: 28,
  md: 36,
  lg: 56,
} as const;

const FULL = {
  sm: { w: 140, h: 48 },
  md: { w: 180, h: 64 },
  lg: { w: 240, h: 88 },
} as const;

export function BrandLogo({
  href = '/',
  variant = 'mark',
  size = 'md',
  showTagline = true,
  className = '',
}: BrandLogoProps) {
  const content =
    variant === 'full' ? (
      <Image
        src="/brand/workpulse-logo.png"
        alt="WorkPulse"
        width={FULL[size].w}
        height={FULL[size].h}
        className="object-contain"
        priority
      />
    ) : (
      <span className={`inline-flex items-center gap-2.5 ${className}`}>
        <Image
          src="/brand/workpulse-mark.png"
          alt="WorkPulse"
          width={MARK[size]}
          height={MARK[size]}
          className="rounded-lg shadow-sm object-cover"
          priority
        />
        <span className="text-left">
          <span className="block font-bold text-slate-900 dark:text-slate-100 text-sm tracking-tight leading-tight">
            WorkPulse
          </span>
          {showTagline && (
            <span className="block text-[10px] text-slate-400 leading-none">Attendance &amp; Leave</span>
          )}
        </span>
      </span>
    );

  if (!href) return <div className={className}>{content}</div>;
  return (
    <Link href={href} className={`inline-flex items-center ${className}`}>
      {content}
    </Link>
  );
}
