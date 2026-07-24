'use client';

import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { CardBrandLogo } from '@/components/billing/CardBrandLogos';
import {
  cardExpired,
  detectBrand,
  formatCardNumber,
  luhnValid,
  sanitize,
} from '@/lib/card';
import { TEST_CARDS } from '@/lib/constants';
import type { CardInput } from '@/types';

const CVC_LENGTH_MIN = 3;
const CVC_LENGTH_MAX = 4;
const MONTH_MIN = 1;
const MONTH_MAX = 12;
const YEAR_MIN = 2024;
const YEAR_MAX = 2100;

interface CardFormProps {
  submitLabel: string;
  submitting: boolean;
  disabled?: boolean;
  onSubmit: (card: CardInput) => void;
}

export function CardForm({ submitLabel, submitting, disabled, onSubmit }: CardFormProps) {
  const [number, setNumber] = useState('');
  const [expMonth, setExpMonth] = useState('');
  const [expYear, setExpYear] = useState('');
  const [cvc, setCvc] = useState('');
  const [holder, setHolder] = useState('');

  const digits = sanitize(number);
  const brand = useMemo(() => detectBrand(digits), [digits]);

  const month = Number(expMonth);
  const year = Number(expYear);

  const numberError =
    digits.length >= 12 && !luhnValid(digits)
      ? 'This card number is not valid.'
      : digits.length >= 12 && brand === undefined
        ? 'Only Visa and Mastercard are accepted.'
        : undefined;

  const expiryError =
    expMonth && expYear && !Number.isNaN(month) && !Number.isNaN(year)
      ? month < MONTH_MIN || month > MONTH_MAX
        ? 'Enter a month between 1 and 12.'
        : year < YEAR_MIN || year > YEAR_MAX
          ? 'Enter a four-digit year.'
          : cardExpired(month, year)
            ? 'This card has expired.'
            : undefined
      : undefined;

  const complete =
    luhnValid(digits) &&
    brand !== undefined &&
    expiryError === undefined &&
    Boolean(expMonth && expYear) &&
    cvc.length >= CVC_LENGTH_MIN &&
    /^\d+$/.test(cvc) &&
    holder.trim().length > 0;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!complete || submitting || disabled) return;
    onSubmit({
      number: digits,
      exp_month: month,
      exp_year: year,
      cvc,
      holder: holder.trim(),
    });
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="relative">
        <Input
          label="Card number"
          module="billing"
          inputMode="numeric"
          autoComplete="cc-number"
          placeholder="4242 4242 4242 4242"
          value={formatCardNumber(number)}
          error={numberError}
          onChange={(e) => setNumber(e.target.value)}
        />
        <span className="pointer-events-none absolute top-8 right-3 text-white">
          <CardBrandLogo brand={brand} />
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Input
          label="Month"
          module="billing"
          inputMode="numeric"
          autoComplete="cc-exp-month"
          placeholder="12"
          maxLength={2}
          value={expMonth}
          onChange={(e) => setExpMonth(e.target.value.replace(/\D/g, ''))}
        />
        <Input
          label="Year"
          module="billing"
          inputMode="numeric"
          autoComplete="cc-exp-year"
          placeholder="2030"
          maxLength={4}
          value={expYear}
          onChange={(e) => setExpYear(e.target.value.replace(/\D/g, ''))}
        />
        <Input
          label="CVC"
          module="billing"
          inputMode="numeric"
          autoComplete="cc-csc"
          placeholder="123"
          maxLength={CVC_LENGTH_MAX}
          value={cvc}
          onChange={(e) => setCvc(e.target.value.replace(/\D/g, ''))}
        />
      </div>

      {expiryError && <p className="text-xs text-danger">{expiryError}</p>}

      <Input
        label="Name on card"
        module="billing"
        autoComplete="cc-name"
        placeholder="A. Person"
        value={holder}
        onChange={(e) => setHolder(e.target.value)}
      />

      <Button
        type="submit"
        module="billing"
        loading={submitting}
        disabled={!complete || disabled}
      >
        {submitLabel}
      </Button>

      <div className="border-t border-border pt-3">
        <p className="text-micro mb-1.5 text-muted">
          No real money moves — the payment provider is a local mock. Test cards:
        </p>
        <ul className="space-y-0.5">
          {TEST_CARDS.map((card) => (
            <li key={card.number} className="font-mono text-xs text-muted">
              &gt; {card.label}: {card.number}
            </li>
          ))}
        </ul>
      </div>
    </form>
  );
}
