package dataprovider;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;

import org.apache.poi.xssf.usermodel.XSSFRow;
import org.apache.poi.xssf.usermodel.XSSFSheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

public class ExcelData  {  
	  private FileInputStream  fis = null; 
	
	// function for creating  file by fileinputstream class 
	  
	public FileInputStream filegetstream () throws FileNotFoundException { 
		
		String filepath ="E:\\ITI\\test Automation\\java-2020-12eclipse\\LevelsetAutomation3\\src\\test\\java\\dataprovider\\Excel_data_driven.xlsx"; 
		   File srcfile = new File(filepath) ; 
		    fis =new FileInputStream(srcfile)  ; 
		    return fis ; 
		    
		    
	}  
	    public Object [] [] Excelreader() throws IOException{  
	    	
	     try {
			 fis = filegetstream() ;
		} catch (FileNotFoundException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}  
	    
	    	
	       // workbook 	     
	    	XSSFWorkbook wb = null;
			try {
				wb = new XSSFWorkbook(fis);
			} catch (IOException e) {
				// TODO Auto-generated catch block
				e.printStackTrace();
			}  
	    	// worksheet  getting the first work sheet in work book 
	    	 XSSFSheet ws = wb.getSheetAt(0) ;  
	    	 int no_ofrows = ws.getLastRowNum()+1 ;
	    	  int no_ofcolumns =  2 ; 
	    	  String [] [] exceldata_array = new String[no_ofrows][no_ofcolumns] ;
	    	  // two for loops to get data for each cell 
	    	   // first loop for rows and second for columns 
	    	    for (int j=0 ;j<no_ofrows ; j++ ) { 
	    	    	for (int i=0 ; i<no_ofcolumns ;i++) {  
	    	    		// worksheet access row 
	    	    		XSSFRow row=  ws.getRow(i); 
	    	    		// row access cell 
	    	    		exceldata_array [j][i] = row.getCell(j).toString();
	    	    	}
	    	    } 
	    	    // close work book 
	    	    wb.close(); 
	    	    return exceldata_array ;
	    	 
	    	
	    }
	
 
}
