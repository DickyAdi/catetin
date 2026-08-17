import { CTAFinal } from "@/components/sections/CTAFinal";
import { ChatScreenshots } from "@/components/sections/ChatScreenshots";
import { FAQ } from "@/components/sections/FAQ";
import { Features } from "@/components/sections/Features";
import { Footer } from "@/components/sections/Footer";
import { Hero } from "@/components/sections/Hero";
import { HowItWorks } from "@/components/sections/HowItWorks";
import { Nav } from "@/components/sections/Nav";
import { Pricing } from "@/components/sections/Pricing";
import { ProblemCards } from "@/components/sections/ProblemCards";
import { Testimonials } from "@/components/sections/Testimonials";

export function Landing() {
  return (
    <div>
      <Nav />
      <Hero />
      <ProblemCards />
      <HowItWorks />
      <ChatScreenshots />
      <Features />
      <Pricing />
      <Testimonials />
      <FAQ />
      <CTAFinal />
      <Footer />
    </div>
  );
}

export default Landing;
