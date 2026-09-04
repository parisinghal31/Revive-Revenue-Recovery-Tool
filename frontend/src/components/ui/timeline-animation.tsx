"use client";
// components/ui/timeline-animation.tsx — blur-reveal sequenced on scroll into view
// (from ui-layouts advanced-stats; adapted to the installed framer-motion package)
import { motion, useInView, type Variants } from "framer-motion";
import type React from "react";

interface TimelineAnimationProps {
  children?: React.ReactNode;
  animationNum: number;
  className?: string;
  timelineRef: React.RefObject<HTMLElement | null>;
  customVariants?: Variants;
  once?: boolean;
}

export const TimelineAnimation = ({
  children, animationNum, timelineRef, className, customVariants, once = true,
}: TimelineAnimationProps) => {
  const defaultSequenceVariants: Variants = {
    visible: (i: number) => ({
      filter: "blur(0px)",
      y: 0,
      opacity: 1,
      transition: { delay: i * 0.5, duration: 0.5 },
    }),
    hidden: { filter: "blur(20px)", y: 0, opacity: 0 },
  };

  const isInView = useInView(timelineRef, { once });

  return (
    <motion.div
      initial="hidden"
      animate={isInView ? "visible" : "hidden"}
      custom={animationNum}
      variants={customVariants || defaultSequenceVariants}
      className={className}
    >
      {children}
    </motion.div>
  );
};
