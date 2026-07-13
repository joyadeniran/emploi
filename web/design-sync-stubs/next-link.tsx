import React from "react";

type LinkProps = React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
  prefetch?: boolean;
  replace?: boolean;
  scroll?: boolean;
  shallow?: boolean;
  children?: React.ReactNode;
};

export default function Link({ href, prefetch, replace, scroll, shallow, ...rest }: LinkProps) {
  void prefetch; void replace; void scroll; void shallow;
  return <a href={href} {...rest} />;
}
