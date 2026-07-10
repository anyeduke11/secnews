import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Routes, Route } from 'react-router-dom';

function HomePage() {
  return <div data-testid="home-page">Home Page</div>;
}

function TodosPage() {
  return <div data-testid="todos-page">Todos Page</div>;
}

function TestApp() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/todos" element={<TodosPage />} />
      </Routes>
    </BrowserRouter>
  );
}

describe('Router integration', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
  });

  it('renders home page at root route', () => {
    render(<TestApp />);
    expect(screen.getByTestId('home-page')).toBeInTheDocument();
  });

  it('renders todos page at /todos route', () => {
    window.history.pushState({}, '', '/todos');
    render(<TestApp />);
    expect(screen.getByTestId('todos-page')).toBeInTheDocument();
  });
});