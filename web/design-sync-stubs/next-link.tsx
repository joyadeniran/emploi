import React from "react";

type LinkProps = React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
  prefetch?: boolean;
  replace?: boolean;
  scroll?: boolean;
  shallow?: boolean;
  children?: React.ReactNode;
};

export default function Link({ href, prefetch: _p, replace: _r, scroll: _s, shallow: _sh, ...rest }: LinkProps) {
  return <a href={href} {...rest} />;
}
