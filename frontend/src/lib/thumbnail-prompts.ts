export type ThumbnailPromptStyle = "reference" | "cinematic-3d";

export function buildThumbnailPrompt(
  title: string,
  part: number,
  language: "vi" | "en",
  style: ThumbnailPromptStyle = "reference",
  titleSource: "text" | "image" = "text",
): string {
  const titleInstruction = titleSource === "image"
    ? language === "en"
      ? "Translate the entire title in the image into English."
      : "Dịch toàn bộ tiêu đề trên hình sang tiếng Việt."
    : language === "en"
      ? `Translate the entire title into English: "${title}".`
      : `Dịch toàn bộ tiêu đề sang tiếng Việt: "${title}".`;
  if (style === "reference") {
    return language === "en"
      ? `@Create image Create a YouTube thumbnail similar to the attached reference image. ${titleInstruction} Use a simple font similar to the original, clear and readable, with text that stands out at small sizes. Use the YouTube thumbnail format 16:9 (1280×720), with harmonious, neutral colors and reduced glare. Add "Part ${part}" in large, clear text at the top right, using the same font as the title. Remove all original text and logos at the top left and top right before adding new text. Preserve the main characters, background and visual style; do not add any new logos or watermarks. Create only one finished image, with no explanation.`
      : `@Tạo hình ảnh Hãy tạo hình giống ảnh tham chiếu đính kèm để làm thumbnail cho video YouTube. ${titleInstruction} Giữ font đơn giản giống với font gốc, rõ ràng, dễ đọc, chữ nổi bật khi xem nhỏ. Chỉnh kích thước đúng thumbnail YouTube 16:9 (1280x720), dùng tông màu hài hòa trung tính, bớt chói. Bổ sung chữ "Phần ${part}" thật to, rõ, cùng font với tiêu đề ở góc trên bên phải. Xóa toàn bộ chữ và logo gốc ở góc trên bên trái và góc trên bên phải trước khi đặt chữ mới. Giữ nguyên nhân vật chính, bối cảnh và phong cách; không thêm logo hoặc watermark mới. Chỉ tạo 1 ảnh hoàn chỉnh, không giải thích.`;
  }

  if (language === "en") {
    return `@Create image Use the attached image as a reference to create a completely new YouTube thumbnail in the style of **High-End Cinematic 3D Anime CGI, Premium Chinese Donghua 3D Rendering**. ${titleInstruction} Use a simple, clear font with cool-toned lettering and prominent highlights that remain readable at small sizes.

**Completely reconstruct the characters as genuine 3D models (Full 3D Character Reconstruction)**, with beautiful, balanced faces, clearly defined volume, ultra-smooth skin (Ultra Smooth Skin, Soft Skin Shading, Subsurface Scattering), soft-looking hair materials (Smooth PBR Materials), and cinematic lighting with smooth light transitions and shadows shaped by the lighting (Soft Cinematic Lighting, Global Illumination). Characters must have spatial depth and naturally rounded contours, like a premium 3D animated film. **Absolutely no 2D Anime Illustration, Digital Painting, Cel Shading, or black outlines.**

Completely change the composition from the original image, retaining only the main characters, outfits, accessories, and key objects. **Group the characters on the right and place the large title on the left**, arranging the characters in multiple layers of 3D depth. Simplify the background, remove unnecessary details, and do not add new characters.

**Leave a Safe Margin/Padding of approximately 5–8% on all four edges**, creating a spacious, balanced composition. Do not place text, faces, or important details close to the edges. Scale the subjects down moderately so the layout is not cramped, keeping all key content within the Safe Area to avoid cropping when the thumbnail is displayed.

Use or shift the palette toward cool tones with subtle orange or red lighting accents. Minimize explosions, smoke, dust, light rays, glowing particles, and complex effects. Avoid oversaturated colors, harsh contrast, glaring light, and shiny plastic-looking skin.

Add **"Part ${part}"** in large, clear, cool-toned but prominent lettering at the top right, using the same font as the title while maintaining a safe distance from the edges. Remove all original text, logos, and watermarks; do not add new logos or watermarks. Ensure all English text is spelled correctly and easy to read.

**Highest priority: Genuine 3D CGI characters, smooth and beautiful faces, clearly defined volume, cinematic depth, a spacious composition, appropriate edge padding, and minimal unnecessary details.**

Standard YouTube thumbnail dimensions: **16:9 (1280×720)**. Create only one finished image, with no explanation.`;
  }

  return `@Tạo hình ảnh Hãy sử dụng ảnh đính kèm làm tham chiếu để tạo một thumbnail YouTube hoàn toàn mới theo phong cách **High-End Cinematic 3D Anime CGI, Premium Chinese Donghua 3D Rendering**. ${titleInstruction} Sử dụng font đơn giản, rõ ràng, màu chữ tông lạnh nhưng highlight nổi bật khi xem nhỏ.

**Dựng lại hoàn toàn các nhân vật dưới dạng mô hình 3D thực thụ (Full 3D Character Reconstruction)**, với khuôn mặt xinh đẹp, cân đối, nổi khối rõ rệt, làn da mịn màng (Ultra Smooth Skin, Soft Skin Shading, Subsurface Scattering), tóc có chất liệu mềm mại (Smooth PBR Materials) và ánh sáng điện ảnh có chuyển vùng và đổ bóng theo vùng sáng (Soft Cinematic Lighting, Global Illumination). Nhân vật phải có chiều sâu không gian, đường nét bo tròn tự nhiên, giống phim hoạt hình 3D cao cấp. **Tuyệt đối không sử dụng phong cách 2D Anime Illustration, Digital Painting, Cel Shading hoặc nét viền đen.**

Thay đổi hoàn toàn bố cục so với ảnh gốc, chỉ giữ lại các nhân vật, trang phục, phụ kiện và vật thể chính. **Dồn nhân vật sang bên phải, đặt tiêu đề lớn bên trái**, sắp xếp các nhân vật theo nhiều lớp chiều sâu 3D. Đơn giản hóa bối cảnh, loại bỏ chi tiết thừa, không thêm nhân vật mới.

**Chừa khoảng đệm an toàn (Safe Margin/Padding) khoảng 5–8% ở cả bốn cạnh ảnh**, tạo không gian thoáng và cân đối. Không đặt chữ, khuôn mặt hoặc các chi tiết quan trọng sát mép ảnh. Thu nhỏ chủ thể vừa phải để bố cục không bị chật chội, đảm bảo toàn bộ nội dung chính nằm gọn trong vùng an toàn (Safe Area), tránh bị cắt khi hiển thị thumbnail.

Sử dụng hoặc giảm màu về tông màu lạnh kết hợp ánh sáng cam hoặc đỏ nhẹ làm điểm nhấn. Giảm tối đa cháy nổ, khói bụi, tia sáng, hạt sáng và hiệu ứng phức tạp. Tránh màu quá rực, tương phản gắt, ánh sáng chói hoặc chất liệu da bóng nhựa.

Thêm chữ **"Phần ${part}"** to, rõ ràng màu sắc tông lạnh nhưng nổi bật ở góc trên bên phải, cùng font với tiêu đề nhưng vẫn đảm bảo khoảng cách an toàn với viền ảnh. Xóa toàn bộ chữ, logo và watermark gốc, không thêm logo hoặc watermark mới. Đảm bảo chữ tiếng Việt đúng chính tả, đầy đủ dấu và dễ đọc.

**Ưu tiên cao nhất: Nhân vật 3D CGI thực sự, khuôn mặt mịn đẹp, nổi khối rõ ràng, chiều sâu điện ảnh, bố cục thoáng, có khoảng đệm viền hợp lý và ít chi tiết thừa.**

Kích thước chuẩn thumbnail YouTube **16:9 (1280×720)**. Chỉ tạo 1 ảnh hoàn chỉnh, không giải thích.`;
}
