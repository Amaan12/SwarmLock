import React from 'react';

export interface ButtonProps {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
}

export const Button: React.FC<ButtonProps> = ({ label, onClick, variant = 'primary' }) => {
  return (
    <button className={`btn btn-${variant}`} onClick={onClick}>
      {label}
    </button>
  );
};

# [2026-10-13 21:53:33] Placeholder edit by Cursor:SubAgent-Frontend - Task: Adding dark mode ripple effect
