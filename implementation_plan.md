# Kế hoạch Triển khai: Tích hợp Giọng nói trực tiếp trên Web Dashboard (Giải pháp C)

Kế hoạch này tập trung triển khai **Giải pháp C: Tích hợp Giọng nói trực tiếp trên Web Dashboard** sử dụng các Web API có sẵn của trình duyệt. Đây là phương án nhanh nhất, tự chủ 100%, không cần kết nối server trung gian hay các thiết bị bên ngoài, đồng thời cho trải nghiệm mượt mà, sang trọng ngay trên Dashboard Next.js.

---

## 🛠 Giải pháp Kỹ thuật (Technical Design)

Chúng ta sẽ tích hợp hoàn toàn tính năng giọng nói trong component [ChatWidget.tsx](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/frontend/components/chatbot/ChatWidget.tsx) của Next.js:

```
                  ┌────────────────────────────────────────┐
                  │           Next.js ChatWidget           │
                  └────┬──────────────────────────────▲────┘
                       │                              │
           [Web Speech API (STT)]             [Web Speech API (TTS)]
           1. Mở microphone                   1. Nhận phản hồi text từ AI
           2. Nhận giọng nói tiếng Việt        2. Lọc bỏ ký tự đặc biệt (*, `)
           3. Chuyển thành text tự động        3. Đọc to câu trả lời bằng vi-VN
                       │                              ▲
                       ▼                              │
             /api/chat REST API                AI Response Text
                       │                              │
                       └────────► [Flask Backend] ────┘
```

### 1. Nhận diện Giọng nói (Speech-to-Text)
*   **Công nghệ:** Sử dụng `window.SpeechRecognition` (hoặc `window.webkitSpeechRecognition` trên các trình duyệt Webkit như Chrome, Safari, Edge).
*   **Cấu hình:** 
    *   `recognition.lang = "vi-VN"` để nhận diện giọng nói Tiếng Việt chuẩn xác.
    *   `recognition.interimResults = false` chỉ lấy kết quả hoàn chỉnh khi người dùng dừng nói.
    *   `recognition.continuous = false` tự động dừng thu âm khi người dùng ngắt câu (tránh thu âm vô hạn gây tốn năng lượng/phiền phức).
*   **Giao diện (UI):** 
    *   Thêm một nút **Microphone (🎙️)** nằm ở phía bên trái của ô nhập liệu (Textarea).
    *   **Hiệu ứng thu âm cực đẹp:** Khi đang ghi âm, nút Micro sẽ nhấp nháy đỏ dạng sóng xung (pulse wave animation), nền nút mờ đi, mang lại cảm giác premium.
    *   Nếu trình duyệt của người dùng không hỗ trợ hoặc họ từ chối quyền truy cập Micro, nút Micro sẽ ẩn hoặc hiển thị trạng thái vô hiệu hóa kèm tooltip giải thích.

### 2. Phát âm phản hồi (Text-to-Speech)
*   **Công nghệ:** Sử dụng `window.speechSynthesis` và đối tượng `SpeechSynthesisUtterance` có sẵn trong tất cả trình duyệt hiện đại.
*   **Cấu hình:**
    *   `utterance.lang = "vi-VN"`
    *   Tìm kiếm và lựa chọn giọng nói Tiếng Việt tốt nhất hiện có trên hệ thống trình duyệt (`speechSynthesis.getVoices()`), ví dụ giọng đọc Google tiếng Việt.
    *   Tốc độ nói (`rate`) đặt mức 1.0 (tự nhiên) và tông giọng (`pitch`) mức 1.0.
*   **Tiền xử lý văn bản:** Phản hồi của Gemini AI thường chứa các định dạng Markdown như dấu hoa thị `**bold**`, dấu code `` `inline` ``, hoặc bullet points. Chúng ta sẽ lọc bỏ các ký hiệu này trước khi đưa vào bộ đọc TTS để giọng nói phát ra trơn tru nhất.
*   **Giao diện (UI):** 
    *   Thêm nút **Bật/Tắt âm thanh (🔊 / 🔇)** trên thanh tiêu đề (Header) của ChatWidget.
    *   Mặc định khi người dùng bấm Micro để hỏi, loa sẽ tự động nói câu trả lời. Nếu người dùng gõ phím, loa sẽ không nói (trừ khi bật nút Auto-read 🔊).
    *   Khi loa đang nói, người dùng có thể nhấp vào nút Loa để **Dừng nói ngay lập tức** (Stop Synthesis).

---

## 📂 Các Tệp Tin Thay đổi (Proposed Changes)

### [Component] [ChatWidget.tsx](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/frontend/components/chatbot/ChatWidget.tsx)
Chúng ta sẽ sửa đổi mã nguồn của tệp `ChatWidget.tsx` để bổ sung logic giọng nói:

1.  **State bổ sung:**
    *   `isListening` (boolean): Theo dõi trạng thái đang thu âm giọng nói.
    *   `isMuted` (boolean): Trạng thái tắt/bật phát âm thanh phản hồi (mặc định false).
    *   `isPlayingSpeech` (boolean): Trạng thái loa đang phát âm.
2.  **Refs:**
    *   `recognitionRef` (ref): Lưu trữ thực thể `SpeechRecognition` để điều khiển bắt đầu/dừng thu âm.
    *   `synthesisRef` (ref): Quản lý luồng nói hiện tại để dừng âm thanh ngay lập tức nếu cần.
3.  **Hàm tiện ích:**
    *   `startListening()`: Xin quyền micro, kích hoạt ghi âm, hiển thị hiệu ứng ghi âm.
    *   `stopListening()`: Tắt ghi âm theo cách thủ công.
    *   `speakText(text: string)`: Nhận văn bản, làm sạch markdown, chọn giọng đọc `vi-VN` chuẩn và phát qua loa.
4.  **Tích hợp vào luồng gửi tin nhắn (`sendMessage`):**
    *   Khi gửi thành công và nhận được `reply` từ `/api/chat`: Nếu người dùng vừa hỏi bằng giọng nói hoặc `!isMuted`, tự động gọi `speakText(reply)`.

---

## 🎨 Giao diện Chi tiết Nút bấm & CSS Premium

*   Nút Mic sẽ được tạo với màu sắc glassmorphism hòa hợp với bảng Slate của Dashboard.
*   Hiệu ứng `pulse-red` khi thu âm:
    ```css
    @keyframes pulse-red {
      0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
      70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
      100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }
    .mic-btn.recording {
      background: #ef4444 !important;
      animation: pulse-red 1.5s infinite;
      color: #fff !important;
    }
    ```

---

## 🧪 Kế hoạch Xác minh & Kiểm thử (Verification Plan)

### Kiểm thử Thủ công (Manual Tests)
1.  **Kiểm tra quyền truy cập Microphone:**
    *   Bấm nút 🎙️ lần đầu tiên. Kiểm tra xem trình duyệt có hiển thị bảng hỏi quyền Micro của Chrome/Safari hay không.
    *   Từ chối quyền và xác nhận giao diện hiển thị thông báo lỗi hoặc vô hiệu hóa nút Mic tinh tế.
    *   Bật lại quyền trong cài đặt trang web và thử nghiệm lại.
2.  **Kiểm tra nhận diện Giọng nói (STT):**
    *   Bấm nút 🎙️, nói câu: *"Hôm nay dùng bao nhiêu số điện"* bằng tiếng Việt rõ ràng.
    *   Xác nhận văn bản tự động điền vào ô input và hệ thống tự kích hoạt gửi tin nhắn đi.
3.  **Kiểm tra chất lượng giọng nói phát ra (TTS):**
    *   Đảm bảo loa đang được bật. Nghe câu trả lời của AI phát ra từ trình duyệt.
    *   Kiểm tra xem các ký tự markdown như `**` hay `-` có bị đọc ra miệng không (đảm bảo hàm `cleanMarkdownForSpeech` hoạt động tốt).
4.  **Kiểm tra nút Bật/Tắt âm thanh (Mute/Unmute):**
    *   Bấm tắt tiếng (🔇), gửi câu hỏi và xác nhận loa không phát ra âm thanh.
    *   Khi loa đang nói dài, bấm nút Mute hoặc nút Dừng và xác nhận loa tắt tiếng ngay lập tức.
