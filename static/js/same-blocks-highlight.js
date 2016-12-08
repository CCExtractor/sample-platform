window.onload = () => {
	let elems = document.getElementsByClassName('diff-same-region');

	for (let i = 0; i < elems.length; i++) {
		let e = elems[i];
		e.onmouseover = () => {
			let pairId = "";
			if (e.id.indexOf("test_result") != -1) {
				pairId = e.id.replace("test_result", "correct");
			} else {
				pairId = e.id.replace("correct", "test_result");
			}
			let pair = document.getElementById(pairId);
			e.style.borderBottom = '1px dotted #3BA3D0';
			pair.style.borderBottom = '1px dotted #3BA3D0';
		}

		e.onmouseout = () => {
			let pairId = "";
			if (e.id.indexOf("test_result") != -1) {
				pairId = e.id.replace("test_result", "correct");
			} else {
				pairId = e.id.replace("correct", "test_result");
			}
			let pair = document.getElementById(pairId);
			e.style.borderBottom = '';
			pair.style.borderBottom = '';
		}
	}
}