import React from 'react';

export const Header: React.FC<{ title: string }> = ({ title }) => {
  return (
    <header className="site-header">
      <h1>{title}</h1>
      <nav>
        <a href="#home">Home</a>
        <a href="#profile">Profile</a>
      </nav>
    </header>
  );
};
