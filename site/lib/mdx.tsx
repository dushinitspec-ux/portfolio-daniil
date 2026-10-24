import "server-only";

import { evaluate } from "@mdx-js/mdx";
import type { MDXComponents } from "mdx/types";
import type { ComponentProps } from "react";
import * as runtime from "react/jsx-runtime";

import { CodeBlock } from "@/components/case/CodeBlock";
import { Diff } from "@/components/case/Diff";
import { Demo, Links, Screenshots, Stack } from "@/components/case/ProjectBlocks";
import { BugPart, Section } from "@/components/case/Section";
import type { Project } from "@/lib/projects";

/**
 * Compile a case study's MDX body at build time and render it with the site's components.
 * Blocks that need frontmatter data (<Demo />, <Screenshots />, ...) get the project bound here,
 * so in MDX they are written without props.
 */
export async function CaseStudyBody({ project }: { project: Project }) {
  const { default: Content } = await evaluate(project.body, { ...runtime, development: false });

  const components: MDXComponents = {
    pre: CodeBlock,
    a: (props: ComponentProps<"a">) => {
      const external = props.href?.startsWith("http");
      return external ? <a {...props} target="_blank" rel="noopener noreferrer" /> : <a {...props} />;
    },
    Section,
    BugPart,
    Diff,
    Demo: () => <Demo project={project} />,
    Screenshots: () => <Screenshots project={project} />,
    Stack: () => <Stack project={project} />,
    Links: () => <Links project={project} />,
  };

  return <Content components={components} />;
}
